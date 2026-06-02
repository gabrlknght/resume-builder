#!/usr/bin/env python3
"""
pipeline.py — Multi-stage resume tailoring pipeline.

Stages:
  1. JD Analysis       — extract structured requirements from the job description
  2. Match & Score     — deterministic keyword overlap scoring (early-exit on low relevance)
  3. Section Tailoring — parallel LLM calls to rewrite profile, experience, projects
  4. Validate & Assemble — run eval-module metrics and auto-fix immutable violations

Each stage yields SSE events for real-time frontend streaming.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import instructor
import openai
from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Eval-module imports
# ---------------------------------------------------------------------------
try:
    sys.path.insert(
        0, str(Path(__file__).resolve().parent.parent / "eval-module" / "eval")
    )
    from metrics import (
        immutable_field_violations,
        run_all_metrics,
        flatten_resume_to_text,
    )  # noqa: E402

    HAS_EVAL_METRICS = True
except Exception:
    HAS_EVAL_METRICS = False


# ---------------------------------------------------------------------------
# Provider configs (mirrors server.py)
# ---------------------------------------------------------------------------
PROVIDER_CONFIGS = {
    "cerebras": {"base_url": "https://api.cerebras.ai/v1"},
    "nvidia": {"base_url": "https://integrate.api.nvidia.com/v1"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"},
    "ollama": {
        "base_url": "http://localhost:11434/v1"
    },
    "openai": {"base_url": None},  # Native OpenAI API
    "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
    "mock": {}
}

# Ollama model alias mapping (short names → full Ollama model IDs)
OLLAMA_MODEL_ALIASES = {
    "lfm2.5": "lfm2.5:latest",
    "gemma4": "gemma4:e4b",
    "gpt-oss": "gpt-oss-20b",
}


# ---------------------------------------------------------------------------
# Instructor client factory
# ---------------------------------------------------------------------------
def get_instructor_client(config: dict):
    provider = config.get("provider", "openai")
    api_key = (config.get("api_key") or "").strip()
    base_url = (config.get("base_url") or "").strip()
    
    # Use default base_url from PROVIDER_CONFIGS if not provided
    if not base_url:
        base_url = PROVIDER_CONFIGS.get(provider, {}).get("base_url")
    
    # Handle Ollama (localhost URL)
    resolved_base_url = base_url
    model = config.get("model", "gpt-4o-mini")
    
    # Resolve Ollama model alias if needed
    if provider == "ollama" and model in OLLAMA_MODEL_ALIASES:
        model = OLLAMA_MODEL_ALIASES[model]
    
    # Ollama uses no auth by default; pass a placeholder key so the openai
    # client doesn't raise a "Missing credentials" error at construction time.
    if provider == "ollama":
        raw_client = openai.OpenAI(
            base_url=resolved_base_url,
            api_key="ollama",
            timeout=60.0
        )
        # Local models often emit multiple parallel tool calls which instructor's
        # TOOLS mode rejects.  JSON mode has the model return a raw JSON object
        # instead, which small/local models handle much more reliably.
        return instructor.from_openai(raw_client, mode=instructor.Mode.JSON)
    else:
        # All other providers need API key and use OpenAI-compatible API
        raw_client = openai.OpenAI(
            api_key=api_key,
            base_url=resolved_base_url
        )
        return instructor.from_openai(raw_client)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


def _parse_if_json_string(v):
    """If v is a JSON-encoded string, parse it into a Python object.

    Smaller LLMs (e.g. llama3.1-8b) sometimes serialize list/dict fields
    as JSON strings inside tool-call arguments.  This validator catches
    that and converts the string back into the expected type before
    Pydantic validates the inner schema.
    """
    if isinstance(v, str):
        # Handle LLM returning literal "null" string
        if v.strip().lower() == "null":
            return None
        try:
            return json.loads(v)
        except (json.JSONDecodeError, ValueError):
            return v
    return v


class JDRequirement(BaseModel):
    skill: str
    category: str
    priority: str
    context: str


class JDAnalysis(BaseModel):
    job_title: str
    company_name: Optional[str] = None
    seniority_level: str
    domain: str
    requirements: list[JDRequirement]
    key_responsibilities: list[str]
    ats_keywords: list[str]

    @field_validator(
        "requirements", "key_responsibilities", "ats_keywords", mode="before"
    )
    @classmethod
    def _parse_json_lists(cls, v):
        return _parse_if_json_string(v)

    @field_validator("company_name", mode="before")
    @classmethod
    def _parse_company_name(cls, v):
        if isinstance(v, str) and v.strip().lower() == "null":
            return None
        return v


class MatchReport(BaseModel):
    relevance_score: int  # 1-10
    matched_requirements: list[JDRequirement]
    gap_requirements: list[JDRequirement]
    matched_keywords: list[str]
    gap_keywords: list[str]
    recommendation: str  # "proceed", "partial", "skip"


class TailoredProfile(BaseModel):
    name: str
    title: str
    bio: str
    avatar: Optional[str] = None
    socials: Optional[dict] = None
    resume: Optional[dict] = None

    @field_validator("socials", "resume", mode="before")
    @classmethod
    def _parse_json_dicts(cls, v):
        return _parse_if_json_string(v)


class TailoredExperienceEntry(BaseModel):
    company: str
    role: str
    startDate: str
    endDate: Optional[str] = None
    location: str
    logo: Optional[str] = None
    details: list[str]

    @field_validator("details", mode="before")
    @classmethod
    def _parse_json_list(cls, v):
        return _parse_if_json_string(v)


class ExperienceList(BaseModel):
    experience: list[TailoredExperienceEntry]

    @field_validator("experience", mode="before")
    @classmethod
    def _parse_json_list(cls, v):
        return _parse_if_json_string(v)


class TailoredProjectEntry(BaseModel):
    title: str
    description: str
    technologies: list[str]
    image: Optional[str] = None
    liveUrl: Optional[str] = None
    status: Optional[str] = None

    @field_validator("technologies", mode="before")
    @classmethod
    def _parse_json_list(cls, v):
        return _parse_if_json_string(v)


class ProjectList(BaseModel):
    projects: list[TailoredProjectEntry]

    @field_validator("projects", mode="before")
    @classmethod
    def _parse_json_list(cls, v):
        return _parse_if_json_string(v)


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------
def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------
def resolve_ollama_model(model_name: str) -> str:
    """Map short model name to Ollama model ID if needed.

    Args:
        model_name (str): Short model name (e.g., "llama3.2")

    Returns:
        str: Full Ollama model ID (e.g., "llama3.2:latest")
    """
    if model_name in OLLAMA_MODEL_ALIASES:
        return OLLAMA_MODEL_ALIASES[model_name]
    return model_name  # Already a full model ID


# ---------------------------------------------------------------------------
# Stage 1: JD Analysis  
# ---------------------------------------------------------------------------
STAGE1_SYSTEM = """You are an expert technical recruiter and hiring manager.
Analyze the job description and extract structured requirements.

For each requirement:
- Identify the specific skill, tool, or qualification
- Categorize it: technical, soft_skill, domain, certification, or experience_years
- Assign priority: must_have (explicitly required), nice_to_have (preferred), bonus (mentioned)
- Provide brief context of how it appears in the JD.
Extract key responsibilities verbatim or near-verbatim from the JD.
Identify ATS keywords that are important for this specific role."""


async def analyze_jd(client, jd_text: str, model: str) -> JDAnalysis:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": STAGE1_SYSTEM},
            {"role": "user", "content": f"Analyze this job description:\n\n{jd_text}"},
        ],
        response_model=JDAnalysis,
        temperature=0.1,
        max_retries=2,
    )
    return response


# ---------------------------------------------------------------------------
# Stage 2: Match & Score (deterministic)
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> set[str]:
    text = text.lower()
    tokens = re.findall(r"[a-z0-9][a-z0-9'/.-]*[a-z0-9]|[a-z0-9]", text)
    return {t for t in tokens if len(t) >= 2}


def _flatten_resume(resume_data: dict) -> str:
    parts: list[str] = []
    profile = resume_data.get("profile", {})
    for field in ("name", "title", "bio"):
        if v := profile.get(field):
            parts.append(str(v))
    for entry in resume_data.get("experience", {}).get("experience", []):
        for field in ("company", "role", "location"):
            if v := entry.get(field):
                parts.append(str(v))
        for detail in entry.get("details", []):
            parts.append(str(detail))
    for project in resume_data.get("projects", {}).get("projects", []):
        for field in ("title", "description"):
            if v := project.get(field):
                parts.append(str(v))
        for tech in project.get("technologies", []):
            parts.append(str(tech))
    return " ".join(parts)


def compute_match_score(resume_data: dict, jd_analysis: JDAnalysis) -> MatchReport:
    resume_tokens = _tokenize(_flatten_resume(resume_data))
    jd_tokens = set()
    for kw in jd_analysis.ats_keywords:
        jd_tokens.update(_tokenize(kw))

    must_haves = [r for r in jd_analysis.requirements if r.priority == "must_have"]
    matched_reqs = []
    gap_reqs = []

    for req in must_haves:
        req_tokens = _tokenize(req.skill)
        if req_tokens & resume_tokens:
            matched_reqs.append(req)
        else:
            gap_reqs.append(req)

    matched_kw = sorted(jd_tokens & resume_tokens)
    gap_kw = sorted(jd_tokens - resume_tokens)

    total = len(must_haves)
    matched = len(matched_reqs)
    relevance = round((matched / total) * 10) if total > 0 else 5

    if relevance <= 2:
        recommendation = "skip"
    elif relevance <= 5:
        recommendation = "partial"
    else:
        recommendation = "proceed"

    return MatchReport(
        relevance_score=relevance,
        matched_requirements=matched_reqs,
        gap_requirements=gap_reqs,
        matched_keywords=matched_kw,
        gap_keywords=gap_kw,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# Stage 3: Section Tailoring
# ---------------------------------------------------------------------------
STAGE3_PROFILE_SYSTEM = """You are an expert technical resume writer.
Rephrase the profile bio and title to better align with the target job description.
Preserve the candidate's name, avatar, socials, and contact info exactly.
Keep the bio professional and concise. Do not invent experience.

IMPORTANT: Use keywords from the job requirements to enhance relevance."""


STAGE3_EXPERIENCE_SYSTEM = """You are an expert technical resume writer.
Rephrase experience bullet points to better align with the target job description.
You may reorder bullets to lead with the most relevant achievements.
Preserve company names, dates, locations, and logos exactly as given.
Do not fabricate experience — only reframe existing achievements with relevant keywords.

IMPORTANT: Use action verbs and quantify results where possible."""


STAGE3_PROJECTS_SYSTEM = """You are an expert technical resume writer.
Rephrase project descriptions to better align with the target job description.
You may reorder technologies to highlight the most relevant ones first (only keep originals).
Preserve project titles, URLs, statuses, and images exactly as given.
Do not invent projects or technologies.

IMPORTANT: Use relevant tech keywords in descriptions to match the target role."""


async def tailor_profile(
    client, profile: dict, jd_analysis: JDAnalysis, model: str
) -> TailoredProfile:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": STAGE3_PROFILE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Job title: {jd_analysis.job_title}\n"
                    f"Key requirements: {[r.skill for r in jd_analysis.requirements if r.priority == 'must_have']}\n"
                    f"Domain: {jd_analysis.domain}\n\n"
                    f"Current profile:\n{json.dumps(profile, indent=2)}"
                ),
            },
        ],
        response_model=TailoredProfile,
        temperature=0.3,
        max_retries=2,
    )
    return response


async def tailor_experience(
    client, experience: dict, jd_analysis: JDAnalysis, model: str
) -> ExperienceList:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": STAGE3_EXPERIENCE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Job title: {jd_analysis.job_title}\n"
                    f"Key requirements: {[r.skill for r in jd_analysis.requirements if r.priority == 'must_have']}\n"
                    f"ATS keywords: {jd_analysis.ats_keywords[:20]}\n\n"
                    f"Current experience:\n{json.dumps(experience.get('experience', []), indent=2)}"
                ),
            },
        ],
        response_model=ExperienceList,
        temperature=0.3,
        max_retries=2,
    )
    return response


async def tailor_projects(
    client, projects: dict, jd_analysis: JDAnalysis, model: str
) -> ProjectList:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": STAGE3_PROJECTS_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Job title: {jd_analysis.job_title}\n"
                    f"Key requirements: {[r.skill for r in jd_analysis.requirements if r.priority == 'must_have']}\n"
                    f"Domain: {jd_analysis.domain}\n\n"
                    f"Current projects:\n{json.dumps(projects.get('projects', []), indent=2)}"
                ),
            },
        ],
        response_model=ProjectList,
        temperature=0.3,
        max_retries=2,
    )
    return response


async def tailor_all_sections(
    client, resume_data: dict, jd_analysis: JDAnalysis, model: str
) -> tuple[dict, list[dict], list[dict]]:
    profile_task = tailor_profile(
        client, resume_data.get("profile", {}), jd_analysis, model
    )
    experience_task = tailor_experience(
        client, resume_data.get("experience", {}), jd_analysis, model
    )
    projects_task = tailor_projects(
        client, resume_data.get("projects", {}), jd_analysis, model
    )
    profile, experience, projects = await asyncio.gather(
        profile_task, experience_task, projects_task
    )
    return profile, experience, projects


# ---------------------------------------------------------------------------
# Stage 4: Validate & Assemble
# ---------------------------------------------------------------------------
def validate_and_assemble(
    original_data: dict,
    profile: TailoredProfile,
    experience: ExperienceList,
    projects: ProjectList,
    jd_text: str,
) -> dict:
    tailored = {
        "profile": profile.model_dump(),
        "experience": {"experience": [e.model_dump() for e in experience.experience]},
        "projects": {"projects": [p.model_dump() for p in projects.projects]},
        "relevance": 0,
        "relevance_analysis": "",
    }

    if HAS_EVAL_METRICS:
        violations = immutable_field_violations(original_data, tailored)
        if violations:
            orig_profile = original_data.get("profile", {})
            tailored["profile"] = {
                **tailored["profile"],
                "name": orig_profile.get("name", tailored["profile"].get("name")),
            }

            orig_exp = original_data.get("experience", {}).get("experience", [])
            for i, (orig, tail) in enumerate(
                zip(orig_exp, tailored["experience"]["experience"])
            ):
                for field in ("company", "startDate", "endDate", "location"):
                    tail[field] = orig.get(field, tail.get(field))

            orig_proj = original_data.get("projects", {}).get("projects", [])
            for i, (orig, tail) in enumerate(
                zip(orig_proj, tailored["projects"]["projects"])
            ):
                for field in ("title", "liveUrl"):
                    tail[field] = orig.get(field, tail.get(field))

        scores = run_all_metrics(original_data, tailored, jd_text)
        tailored["eval_scores"] = scores

    return tailored


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------
async def run_pipeline(client, model: str, jd_text: str, resume_data: dict):
    try:
        yield sse_event(
            {
                "stage": 1,
                "status": "in_progress",
                "message": "Analyzing job description...",
            }
        )
        jd_analysis = await analyze_jd(client, jd_text, model)
        yield sse_event(
            {
                "stage": 1,
                "status": "complete",
                "data": {
                    "job_title": jd_analysis.job_title,
                    "requirements_count": len(jd_analysis.requirements),
                    "ats_keywords": jd_analysis.ats_keywords[:10],
                },
            }
        )

        yield sse_event(
            {
                "stage": 2,
                "status": "in_progress",
                "message": "Matching resume to requirements...",
            }
        )
        match_report = compute_match_score(resume_data, jd_analysis)
        yield sse_event(
            {
                "stage": 2,
                "status": "complete",
                "data": {
                    "relevance": match_report.relevance_score,
                    "matched": len(match_report.matched_keywords),
                    "gaps": len(match_report.gap_keywords),
                    "recommendation": match_report.recommendation,
                },
            }
        )

        if match_report.relevance_score <= 2:
            yield sse_event(
                {
                    "stage": "final",
                    "status": "skip",
                    "data": {
                        "profile": resume_data.get("profile", {}),
                        "experience": resume_data.get("experience", {}),
                        "projects": resume_data.get("projects", {}),
                        "relevance": match_report.relevance_score,
                        "relevance_analysis": (
                            f"Very low match ({match_report.relevance_score}/10). "
                            f"Missing: {', '.join(match_report.gap_keywords[:5])}"
                        ),
                        "eval_scores": {
                            "overall_pass": False,
                            "recommendation": "skip",
                        },
                    },
                }
            )
            return

        yield sse_event(
            {
                "stage": 3,
                "status": "in_progress",
                "message": "Tailoring resume sections...",
            }
        )
        profile, experience, projects = await tailor_all_sections(
            client, resume_data, jd_analysis, model
        )
        yield sse_event({"stage": 3, "status": "complete"})

        yield sse_event(
            {
                "stage": 4,
                "status": "in_progress",
                "message": "Validating output...",
            }
        )
        final = validate_and_assemble(
            resume_data, profile, experience, projects, jd_text
        )

        final["relevance"] = match_report.relevance_score
        final["relevance_analysis"] = (
            f"Match: {match_report.relevance_score}/10. "
            f"Matched: {', '.join(match_report.matched_keywords[:8])}. "
            f"Gaps: {', '.join(match_report.gap_keywords[:5])}."
        )
        final["jd_analysis"] = {
            "job_title": jd_analysis.job_title,
            "requirements_count": len(jd_analysis.requirements),
            "ats_keywords": jd_analysis.ats_keywords,
        }

        yield sse_event({"stage": 4, "status": "complete"})
        yield sse_event({"stage": "final", "status": "complete", "data": final})

    except Exception as e:
        import traceback

        traceback.print_exc()
        # Extract a clean error message
        msg = str(e)
        if "InstructorRetryException" in type(e).__name__ or "<failed_attempts>" in msg:
            # Get the root cause from the last exception in the retry chain
            cause = e.__cause__
            if cause:
                msg = str(cause)
            else:
                # Strip XML-ish tags from instructor error
                msg = re.sub(r"<[^>]+>", " ", msg).strip()[:500]
        yield sse_event({"status": "error", "message": msg})
