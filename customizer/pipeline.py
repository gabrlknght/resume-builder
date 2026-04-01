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
from pydantic import BaseModel

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
    "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
    "openai": {"base_url": None},
}


# ---------------------------------------------------------------------------
# Instructor client factory
# ---------------------------------------------------------------------------
def get_instructor_client(config: dict):
    provider = config.get("provider", "openai")
    api_key = config.get("api_key", "").strip()
    base_url = config.get("base_url", "").strip()
    if not base_url:
        base_url = PROVIDER_CONFIGS.get(provider, {}).get("base_url")
    raw_client = openai.OpenAI(api_key=api_key, base_url=base_url)
    return instructor.from_openai(raw_client)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class JDRequirement(BaseModel):
    skill: str
    category: (
        str  # "technical", "soft_skill", "domain", "certification", "experience_years"
    )
    priority: str  # "must_have", "nice_to_have", "bonus"
    context: str


class JDAnalysis(BaseModel):
    job_title: str
    company_name: Optional[str] = None
    seniority_level: str
    domain: str
    requirements: list[JDRequirement]
    key_responsibilities: list[str]
    ats_keywords: list[str]


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


class TailoredExperienceEntry(BaseModel):
    company: str
    role: str
    startDate: str
    endDate: Optional[str] = None
    location: str
    logo: Optional[str] = None
    details: list[str]


class ExperienceList(BaseModel):
    experience: list[TailoredExperienceEntry]


class TailoredProjectEntry(BaseModel):
    title: str
    description: str
    technologies: list[str]
    image: Optional[str] = None
    liveUrl: Optional[str] = None
    status: Optional[str] = None


class ProjectList(BaseModel):
    projects: list[TailoredProjectEntry]


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------
def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Stage 1: JD Analysis
# ---------------------------------------------------------------------------
STAGE1_SYSTEM = """You are an expert technical recruiter and hiring manager.
Analyze the job description and extract structured requirements.

For each requirement:
- Identify the specific skill, tool, or qualification
- Categorize it: technical, soft_skill, domain, certification, or experience_years
- Assign priority: must_have (explicitly required), nice_to_have (preferred), bonus (mentioned)
- Provide brief context of how it appears in the JD

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
Keep the bio professional and concise. Do not invent experience."""


STAGE3_EXPERIENCE_SYSTEM = """You are an expert technical resume writer.
Rephrase experience bullet points to better align with the target job description.
You may reorder bullets to lead with the most relevant achievements.
Preserve company names, dates, locations, and logos exactly as given.
Do not fabricate experience — only reframe existing achievements with relevant keywords."""


STAGE3_PROJECTS_SYSTEM = """You are an expert technical resume writer.
Rephrase project descriptions to better align with the target job description.
You may reorder technologies to highlight the most relevant ones first (only keep originals).
Preserve project titles, URLs, statuses, and images exactly as given.
Do not invent projects or technologies."""


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
                "stage": "analysis",
                "status": "started",
                "message": "Analyzing job description...",
            }
        )
        jd_analysis = await analyze_jd(client, jd_text, model)
        yield sse_event(
            {
                "stage": "analysis",
                "status": "completed",
                "data": jd_analysis.model_dump(),
                "message": f"Found {len(jd_analysis.requirements)} requirements",
            }
        )

        yield sse_event(
            {
                "stage": "match",
                "status": "started",
                "message": "Computing match score...",
            }
        )
        match_report = compute_match_score(resume_data, jd_analysis)
        yield sse_event(
            {
                "stage": "match",
                "status": "completed",
                "data": match_report.model_dump(),
                "message": f"Relevance: {match_report.relevance_score}/10 ({match_report.recommendation})",
            }
        )

        if match_report.relevance_score <= 2:
            yield sse_event(
                {
                    "stage": "abort",
                    "status": "skipped",
                    "message": f"Resume relevance too low ({match_report.relevance_score}/10). Skipping tailoring.",
                }
            )
            return

        yield sse_event(
            {
                "stage": "tailor",
                "status": "started",
                "message": "Tailoring resume sections...",
            }
        )
        profile, experience, projects = await tailor_all_sections(
            client, resume_data, jd_analysis, model
        )
        yield sse_event(
            {
                "stage": "tailor",
                "status": "completed",
                "message": "All sections tailored successfully",
            }
        )

        yield sse_event(
            {
                "stage": "validate",
                "status": "started",
                "message": "Validating and assembling...",
            }
        )
        final = validate_and_assemble(
            resume_data, profile, experience, projects, jd_text
        )
        yield sse_event(
            {
                "stage": "validate",
                "status": "completed",
                "data": final,
                "message": "Pipeline complete",
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        yield sse_event({"stage": "error", "status": "failed", "message": str(e)})
