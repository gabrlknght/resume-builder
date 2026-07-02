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
import re
import sys
from pathlib import Path
from typing import Any, Optional

import instructor
import openai
from pydantic import BaseModel, field_validator, model_validator

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
    "llamacpp": {
        "base_url": "http://localhost:8080"  # no /v1 prefix — server expects plain host:port
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1"
    },
    "openai": {"base_url": None},  # Native OpenAI API
    "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
    "mock": {}
}

# Ollama model alias mapping (short names -> full Ollama model IDs)
OLLAMA_MODEL_ALIASES = {
    "lfm2.5": "lfm2.5:latest",
    "gemma4": "gemma4-opencode:latest",
    "qwen3.5": "qwen3.5-opencode:latest",
    "gpt-oss": "gpt-oss-20b",
}

# Hard ceiling on generated tokens per call. Reasoning models spend a chunk
# of this on hidden <think> chains before the final JSON, so this needs
# headroom beyond the structured output itself.
MAX_OUTPUT_TOKENS = 6144


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

    resolved_base_url = base_url
    # Model alias resolution is handled by resolve_ollama_model() (applied before run_pipeline).
    # Ollama uses no auth by default; pass a placeholder key so the openai
    # client doesn't raise a "Missing credentials" error at construction time.
    if provider == "ollama":
        raw_client = openai.AsyncOpenAI(
            base_url=resolved_base_url,
            api_key="ollama",
            timeout=60.0
        )
        # Local models often emit multiple parallel tool calls which instructor's
        # TOOLS mode rejects.  JSON mode has the model return a raw JSON object
        # instead, which small/local models handle much more reliably.
        return instructor.from_openai(raw_client, mode=instructor.Mode.JSON)
    elif provider == "llamacpp":
        raw_client = openai.AsyncOpenAI(
            api_key=(api_key or "llamacpp"),
            base_url=resolved_base_url,
            timeout=120.0,  # local models can stall on OOM / context overflow
        )
        # Local models often emit multiple parallel tool calls which instructor's
        # TOOLS mode rejects.  JSON mode has the model return a raw JSON object
        # instead, which small/local models handle much more reliably.
        return instructor.from_openai(raw_client, mode=instructor.Mode.JSON)
    else:
        # All other providers need API key and use OpenAI-compatible API
        raw_client = openai.AsyncOpenAI(
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
    semantic_concepts: list[str]
    tone_cues: str

    @field_validator(
        "requirements", "key_responsibilities", "ats_keywords", "semantic_concepts", mode="before"
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

    @model_validator(mode="before")
    @classmethod
    def unwrap_properties(cls, data: Any) -> Any:
        """Some local models (e.g. gemma4) mirror the JSON Schema structure and
        wrap output fields inside a 'properties' envelope.  Unwrap it so
        Pydantic sees the fields at the expected root level."""
        if isinstance(data, dict) and "properties" in data and isinstance(data["properties"], dict):
            return data["properties"]
        return data

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
# Cover Letter models
# ---------------------------------------------------------------------------
class CoverLetterOutput(BaseModel):
    subject_line: str
    salutation: str
    opening_paragraph: str
    body_paragraphs: list[str]
    closing_paragraph: str
    sign_off: str
    improvements_from_prior: Optional[list[str]] = None

    @model_validator(mode="before")
    @classmethod
    def unwrap_envelope(cls, data: Any) -> Any:
        """Handle two common local-model output mistakes:
        1. 'properties' wrapping — model mirrors the JSON Schema structure.
        2. 'thought' leaking — model emits its chain-of-thought as the root key
           instead of the actual fields (seen in gemma4 retry attempts).
        In both cases, unwrap to the real content dict if found inside."""
        if not isinstance(data, dict):
            return data
        # Unwrap {"properties": {...actual fields...}}
        if "properties" in data and isinstance(data["properties"], dict):
            return data["properties"]
        # Strip {"thought": "...", ...} — drop the thought key and keep the rest,
        # or if thought is the ONLY key and its value is a string (pure leakage),
        # there's nothing to recover — let Pydantic raise the normal error.
        if "thought" in data:
            cleaned = {k: v for k, v in data.items() if k != "thought"}
            if cleaned:
                return cleaned
        return data

    @field_validator("body_paragraphs", "improvements_from_prior", mode="before")
    @classmethod
    def _parse_json_lists(cls, v):
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
STAGE1_SYSTEM = """You are a world-class Executive Resume Writer and ATS Algorithm Expert.
Analyze the job description and extract structured requirements using Semantic ATS Mapping.

For each requirement:
- Identify the specific skill, tool, or qualification
- Categorize it: technical, soft_skill, domain, certification, or experience_years
- Assign priority: must_have (explicitly required), nice_to_have (preferred), bonus (mentioned)
- Provide brief context of how it appears in the JD.
Extract key responsibilities verbatim or near-verbatim from the JD.
Identify top 10-15 ATS keywords that are critical for this role.

Additionally, extract:
- Semantic concepts: broader thematic concepts beyond exact keywords (e.g., "cross-functional leadership", "data-driven decision making", "agile transformation", "stakeholder communication"). These are conceptual competencies the role demands, even if not phrased as explicit skills.
- Tone cues: analyze the JD's language to infer the desired tone (e.g., "formal and authoritative", "energetic and innovative", "collaborative and warm", "technical and precise"). Return 2-3 sentences describing the tone signals you observed in the JD.

Return exactly one JSON object matching the schema below — do NOT include any reasoning or explanation text outside the JSON."""


async def analyze_jd(client, jd_text: str, model: str) -> JDAnalysis:
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": STAGE1_SYSTEM},
            {"role": "user", "content": f"Analyze this job description:\n\n{jd_text}"},
        ],
        response_model=JDAnalysis,
        temperature=0.1,
        max_retries=2,
        max_tokens=MAX_OUTPUT_TOKENS,
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
STAGE3_REWRITE_STRATEGY = """You are a world-class Executive Resume Writer and ATS Algorithm Expert specializing in Semantic ATS Mapping.

Your job: naturally embed high-value keywords and semantic concepts from the target role into the resume sections provided below. Do NOT stuff keywords awkwardly — the result must read authentically and highlight real achievements.

Rewriting strategy:
- Prioritize keywords and concepts from the JD's "must_have" requirements
- Map semantic concepts, not just exact strings (e.g., "cross-functional leadership" can cover "led teams across departments")
- Use action verbs and quantify results where possible
- Lead with impact — achievement-focused phrasing

Preservation rules (never change):
- Company names, dates, locations, URLs, logos — keep exactly as given
- Project titles and live URLs — keep exactly as given
- Candidate's name and contact info — keep exactly as given

Honesty rules (never violate):
- Do NOT invent skills, experiences, metrics, or technologies not present or strongly implied in the original
- Do NOT fabricate achievements — reframe existing ones, don't create new ones

Tone: {tone}

OUTPUT FORMAT: Return a flat JSON object with fields at the root level.
Do NOT wrap fields inside a "properties" key.
Correct:   {{"name": "...", "title": "...", "bio": "..."}}
Incorrect: {{"properties": {{"name": "...", "title": "...", "bio": "..."}}}}

Do NOT include any "thought", reasoning, or explanation text outside the JSON."""


STAGE3_PROFILE_STRATEGY = STAGE3_REWRITE_STRATEGY + "\n\nRewrite the profile section (bio and title) to align with the target role while preserving the candidate's identity and core expertise."

STAGE3_EXPERIENCE_STRATEGY = STAGE3_REWRITE_STRATEGY + """

Experience-specific rules:
- You may reorder bullets within a role to lead with the most ATS-relevant achievements
- Preserve company names, dates, locations, logos, and role start/end dates exactly
- Quantify impact using: [Action Verb] + [What] + [How] + [Result]"""

STAGE3_PROJECTS_STRATEGY = STAGE3_REWRITE_STRATEGY + """

Projects-specific rules:
- You may reorder the technologies list to surface the most role-relevant ones first, but only keep technologies already present — do not add new ones
- Preserve project titles, live URLs, images, and status fields exactly as given
- Keep descriptions concise and focused on technical impact"""


def _tailor_context(jd_analysis: JDAnalysis, tone: str, section_type: str) -> dict:
    """Build the shared context dict for Stage 3 section calls."""
    must_haves = [r.skill for r in jd_analysis.requirements if r.priority == "must_have"]
    semantic = jd_analysis.semantic_concepts if jd_analysis.semantic_concepts else []

    ctx = {
        "tone": tone,
        "job_title": jd_analysis.job_title,
        "domain": jd_analysis.domain,
        "must_have": must_haves,
        "semantic_concepts": semantic,
        "tone_cues": jd_analysis.tone_cues or "",
    }
    if section_type == "experience":
        ctx["ats_keywords"] = jd_analysis.ats_keywords[:20]
    return ctx


async def tailor_profile(
    client, profile: dict, jd_analysis: JDAnalysis, model: str, tone: str = "professional"
) -> TailoredProfile:
    ctx = _tailor_context(jd_analysis, tone, "profile")
    strategy = STAGE3_PROFILE_STRATEGY.format(**ctx)
    tone_cues_line = f"JD tone cues: {ctx['tone_cues']}\n" if ctx["tone_cues"] else ""
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": strategy},
            {
                "role": "user",
                "content": (
                    f"Job title: {jd_analysis.job_title}\n"
                    f"Key requirements: {ctx['must_have']}\n"
                    f"Semantic concepts: {ctx['semantic_concepts']}\n"
                    f"Domain: {ctx['domain']}\n"
                    + tone_cues_line
                    + f"\nCurrent profile:\n{json.dumps(profile, indent=2)}"
                ),
            },
        ],
        response_model=TailoredProfile,
        temperature=0.3,
        max_retries=2,
        max_tokens=MAX_OUTPUT_TOKENS,
    )
    return response


async def tailor_experience(
    client, experience: dict, jd_analysis: JDAnalysis, model: str, tone: str = "professional"
) -> ExperienceList:
    ctx = _tailor_context(jd_analysis, tone, "experience")
    strategy = STAGE3_EXPERIENCE_STRATEGY.format(**ctx)
    tone_cues_line = f"JD tone cues: {ctx['tone_cues']}\n" if ctx["tone_cues"] else ""
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": strategy},
            {
                "role": "user",
                "content": (
                    f"Job title: {jd_analysis.job_title}\n"
                    f"Key requirements: {ctx['must_have']}\n"
                    f"ATS keywords: {ctx['ats_keywords']}\n"
                    f"Semantic concepts: {ctx['semantic_concepts']}\n"
                    f"Domain: {ctx['domain']}\n"
                    + tone_cues_line
                    + f"\nCurrent experience:\n{json.dumps(experience.get('experience', []), indent=2)}"
                ),
            },
        ],
        response_model=ExperienceList,
        temperature=0.3,
        max_retries=2,
        max_tokens=MAX_OUTPUT_TOKENS,
    )
    return response


async def tailor_projects(
    client, projects: dict, jd_analysis: JDAnalysis, model: str, tone: str = "professional"
) -> ProjectList:
    ctx = _tailor_context(jd_analysis, tone, "projects")
    strategy = STAGE3_PROJECTS_STRATEGY.format(**ctx)
    tone_cues_line = f"JD tone cues: {ctx['tone_cues']}\n" if ctx["tone_cues"] else ""
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": strategy},
            {
                "role": "user",
                "content": (
                    f"Job title: {jd_analysis.job_title}\n"
                    f"Key requirements: {ctx['must_have']}\n"
                    f"Semantic concepts: {ctx['semantic_concepts']}\n"
                    f"Domain: {ctx['domain']}\n"
                    + tone_cues_line
                    + f"\nCurrent projects:\n{json.dumps(projects.get('projects', []), indent=2)}"
                ),
            },
        ],
        response_model=ProjectList,
        temperature=0.3,
        max_retries=2,
        max_tokens=MAX_OUTPUT_TOKENS,
    )
    return response


async def tailor_all_sections(
    client, resume_data: dict, jd_analysis: JDAnalysis, model: str, tone: str = "professional"
) -> tuple[dict, list[dict], list[dict]]:
    profile_task = tailor_profile(
        client, resume_data.get("profile", {}), jd_analysis, model, tone
    )
    experience_task = tailor_experience(
        client, resume_data.get("experience", {}), jd_analysis, model, tone
    )
    projects_task = tailor_projects(
        client, resume_data.get("projects", {}), jd_analysis, model, tone
    )
    profile, experience, projects = await asyncio.gather(
        profile_task, experience_task, projects_task
    )
    return profile, experience, projects


# ---------------------------------------------------------------------------
# Stage 4: Validate & Assemble
# ---------------------------------------------------------------------------
def build_keyword_matrix(
    original_data: dict,
    tailored_sections: dict,
    jd_analysis: JDAnalysis,
) -> list[dict]:
    """Deterministic keyword mapping matrix.

    For each tailored bullet/description, record every JD keyword it contains.
    Pairs the tailored text with the original at the same position as best-effort
    context — no positional diff assumption, no single-keyword-per-bullet limit.
    """
    matrix = []
    keywords = jd_analysis.ats_keywords[:15]
    if not keywords:
        return matrix

    def _truncate(s: str, n: int = 120) -> str:
        return s[:n] + ("..." if len(s) > n else "")

    orig_exp = original_data.get("experience", {}).get("experience", [])
    tail_exp = tailored_sections.get("experience", {}).get("experience", [])

    for i in range(min(len(orig_exp), len(tail_exp))):
        orig_bullets = orig_exp[i].get("details", [])
        tail_bullets = tail_exp[i].get("details", [])
        context = f"{tail_exp[i].get('role', '')} at {tail_exp[i].get('company', '')}"

        for j, tail_text in enumerate(tail_bullets):
            orig_text = orig_bullets[j] if j < len(orig_bullets) else ""
            for kw in keywords:
                if kw.lower() in tail_text.lower():
                    matrix.append({
                        "extracted_keyword": kw,
                        "original_phrasing": _truncate(orig_text),
                        "new_position": _truncate(tail_text),
                        "context": context,
                    })

    orig_proj = original_data.get("projects", {}).get("projects", [])
    tail_proj = tailored_sections.get("projects", {}).get("projects", [])

    for i in range(min(len(orig_proj), len(tail_proj))):
        orig_desc = orig_proj[i].get("description", "")
        tail_desc = tail_proj[i].get("description", "")
        if orig_desc != tail_desc:
            for kw in keywords:
                if kw.lower() in tail_desc.lower():
                    matrix.append({
                        "extracted_keyword": kw,
                        "original_phrasing": _truncate(orig_desc),
                        "new_position": _truncate(tail_desc),
                        "context": tail_proj[i].get("title", ""),
                    })

    # Deduplicate by (keyword, new_position)
    seen: set[tuple[str, str]] = set()
    unique = []
    for m in matrix:
        key = (m["extracted_keyword"], m["new_position"][:80])
        if key not in seen:
            seen.add(key)
            unique.append(m)

    return unique


def validate_and_assemble(
    original_data: dict,
    profile: TailoredProfile,
    experience: ExperienceList,
    projects: ProjectList,
    jd_text: str,
    keyword_matrix: Optional[list[dict]] = None,
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

    # Add keyword mapping to final output
    if keyword_matrix is not None:
        tailored["keyword_mapping"] = keyword_matrix

    return tailored


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------
async def run_pipeline(client, model: str, jd_text: str, resume_data: dict, tone: str = "professional"):
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
            client, resume_data, jd_analysis, model, tone
        )
        yield sse_event({"stage": 3, "status": "complete"})

        # Stage 3.5: Keyword Mapping Matrix
        yield sse_event(
            {
                "stage": 3.5,
                "status": "in_progress",
                "message": "Building keyword mapping matrix...",
            }
        )
        keyword_matrix = build_keyword_matrix(
            resume_data,
            {"profile": profile.model_dump(), "experience": experience.model_dump(), "projects": projects.model_dump()},
            jd_analysis,
        )
        yield sse_event({"stage": 3.5, "status": "complete"})

        yield sse_event(
            {
                "stage": 4,
                "status": "in_progress",
                "message": "Validating output...",
            }
        )
        final = validate_and_assemble(
            resume_data, profile, experience, projects, jd_text, keyword_matrix
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


# ---------------------------------------------------------------------------
# Cover Letter: system prompt & generator
# ---------------------------------------------------------------------------
COVER_LETTER_SYSTEM = """You are an expert career coach and professional writer specialising in targeted cover letters.

Given the candidate's resume data, the analyzed job description, and optionally a prior cover letter,
write a compelling, personalised cover letter.

Rules:
- 3-4 paragraphs: strong opening hook, relevant experience proof, value proposition, call-to-action close
- Mirror ATS keywords from the JD naturally — never stuff them awkwardly
- Highlight 2-3 specific, quantified achievements from the resume that directly address the role
- Tone: {tone} — let this shape word choice, sentence rhythm, and formality throughout
- Avoid stiff boilerplate phrases like "I am writing to express my interest"
- Opening: reference the specific role AND company; lead with a compelling hook
- If a prior cover letter is provided: preserve the candidate's authentic voice but sharpen relevance,
  fix weaknesses, and ensure all key JD requirements are addressed. List improvements in improvements_from_prior.
- sign_off should be natural e.g. "Sincerely," or "Best regards,"

Output must be a complete, ready-to-send cover letter split into the structured fields.

OUTPUT FORMAT: Return a flat JSON object with fields at the root level.
Do NOT wrap fields inside a "properties" key. Do NOT include a "thought" or reasoning key.
Correct:   {{"subject_line": "...", "salutation": "...", "opening_paragraph": "..."}}
Incorrect: {{"properties": {{"subject_line": "..."}}}}
Incorrect: {{"thought": "...", "subject_line": "..."}}"""


async def generate_cover_letter(
    client,
    model: str,
    jd_text: str,
    jd_analysis: JDAnalysis,
    resume_data: dict,
    prior_letter: Optional[str] = None,
    tone: str = "professional",
) -> CoverLetterOutput:
    profile = resume_data.get("profile", {})
    candidate_name = profile.get("name", "the candidate")
    candidate_title = profile.get("title", "")
    candidate_bio = profile.get("bio", "")

    exp_lines: list[str] = []
    for entry in resume_data.get("experience", {}).get("experience", []):
        highlights = entry.get("details", [])[:2]
        exp_lines.append(
            f"{entry.get('role', '')} at {entry.get('company', '')}: {'; '.join(highlights)}"
        )

    prior_section = ""
    if prior_letter and prior_letter.strip():
        prior_section = (
            "\n\nPRIOR COVER LETTER (use as stylistic basis — improve and tailor to this JD):\n"
            + prior_letter.strip()
        )

    user_msg = (
        f"Candidate: {candidate_name}, {candidate_title}\n"
        f"Summary: {candidate_bio}\n\n"
        f"Experience highlights:\n"
        + "\n".join(f"- {e}" for e in exp_lines)
        + f"\n\nTarget role: {jd_analysis.job_title} at {jd_analysis.company_name or 'the company'}\n"
        f"Must-have requirements: {[r.skill for r in jd_analysis.requirements if r.priority == 'must_have'][:8]}\n"
        f"Domain: {jd_analysis.domain}\n"
        f"ATS keywords: {jd_analysis.ats_keywords[:15]}\n\n"
        f"Job Description (excerpt):\n{jd_text[:2500]}"
        + prior_section
    )

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": COVER_LETTER_SYSTEM.format(tone=tone)},
            {"role": "user", "content": user_msg},
        ],
        response_model=CoverLetterOutput,
        temperature=0.4,
        max_retries=2,
        max_tokens=MAX_OUTPUT_TOKENS,
    )
    return response


async def run_cover_letter_pipeline(
    client,
    model: str,
    jd_text: str,
    resume_data: dict,
    prior_letter: Optional[str] = None,
    tone: str = "professional",
):
    try:
        yield sse_event(
            {"stage": 1, "status": "in_progress", "message": "Analyzing job description..."}
        )
        jd_analysis = await analyze_jd(client, jd_text, model)
        yield sse_event(
            {
                "stage": 1,
                "status": "complete",
                "data": {
                    "job_title": jd_analysis.job_title,
                    "company": jd_analysis.company_name or "",
                    "requirements_count": len(jd_analysis.requirements),
                },
            }
        )

        yield sse_event(
            {"stage": 2, "status": "in_progress", "message": "Matching resume credentials to role..."}
        )
        match_report = compute_match_score(resume_data, jd_analysis)
        yield sse_event(
            {
                "stage": 2,
                "status": "complete",
                "data": {
                    "relevance": match_report.relevance_score,
                    "matched_keywords": match_report.matched_keywords[:10],
                },
            }
        )

        stage3_msg = (
            "Refining cover letter from prior draft..."
            if prior_letter and prior_letter.strip()
            else "Writing cover letter..."
        )
        yield sse_event({"stage": 3, "status": "in_progress", "message": stage3_msg})
        cover_letter = await generate_cover_letter(
            client, model, jd_text, jd_analysis, resume_data, prior_letter, tone
        )
        yield sse_event({"stage": 3, "status": "complete"})

        yield sse_event(
            {
                "stage": "final",
                "status": "complete",
                "data": {
                    "subject_line": cover_letter.subject_line,
                    "salutation": cover_letter.salutation,
                    "opening_paragraph": cover_letter.opening_paragraph,
                    "body_paragraphs": cover_letter.body_paragraphs,
                    "closing_paragraph": cover_letter.closing_paragraph,
                    "sign_off": cover_letter.sign_off,
                    "improvements_from_prior": cover_letter.improvements_from_prior or [],
                    "job_title": jd_analysis.job_title,
                    "company": jd_analysis.company_name or "",
                    "relevance": match_report.relevance_score,
                    "candidate_name": resume_data.get("profile", {}).get("name", ""),
                    "tone": tone,
                },
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        msg = str(e)
        if "InstructorRetryException" in type(e).__name__ or "<failed_attempts>" in msg:
            cause = e.__cause__
            if cause:
                msg = str(cause)
            else:
                msg = re.sub(r"<[^>]+>", " ", msg).strip()[:500]
        yield sse_event({"status": "error", "message": msg})
