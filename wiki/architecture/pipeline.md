---
title: AI Tailoring Pipeline
type: architecture
last_updated: 2026-06-16
sources: [AGENTS.md, customizer/pipeline.py, customizer/TAILOR_SKILL.md]
---

# AI Tailoring Pipeline

The `/api/tailor` endpoint implements a 4-stage pipeline that replaces the original single-prompt approach. Each stage has a focused responsibility and dedicated cost profile.

## Stages

```
Stage 1: JD Analysis       — Extracts structured requirements from JD text
                             LLM call, temperature=0.1
Stage 2: Match & Score     — Deterministic keyword matching, no LLM cost
                             Early exit if relevance ≤ 2
Stage 3: Section Tailoring — 3 parallel LLM calls via asyncio.gather
                             (profile, experience, projects)
Stage 4: Validate & Assemble — Pydantic validation + immutable field checks + eval metrics
```

## Key Design Choices

**Structured output via `instructor`** — Pydantic models define expected LLM output shape. `instructor` handles automatic retry on validation failures. No manual JSON parsing.

**BYOK (Bring Your Own Key)** — User selects provider (OpenAI, Gemini, Cerebras, OpenRouter), model, and API key via UI. The pipeline adapts to the chosen provider.

**SSE progress streaming** — Each stage emits a Server-Sent Event when it completes. The UI updates a progress bar stage-by-stage. No opaque spinner.

**Immutable field protection** — After Stage 3, Stage 4 auto-restores any LLM-mutated immutable fields:
- Company names
- Dates (startDate, endDate)
- Locations
- URLs (liveUrl, socials, etc.)

**Parallel tailoring** — Stage 3 runs three LLM calls concurrently (`asyncio.gather`) for profile, experience, and projects. Reduces latency vs. sequential calls.

**Eval metrics** — Stage 4 computes:
- `job_alignment_score` — how well tailored output matches JD keywords
- `content_preservation` — how much original content was kept
- `hallucinated_numbers` — detected fabricated metrics (should be 0)

## Tailoring Rules (from TAILOR_SKILL.md)

**Can be changed:**
- `profile.title` — match JD role title
- `profile.bio` — emphasize JD-relevant experience
- `experience[].role` — match JD title
- `experience[].details[]` — reorder and rephrase bullets
- `projects[].description` — emphasize JD-relevant tech
- `projects[].technologies[]` — reorder priority
- `contact.availability` — tailor to JD

**Never changed (immutable):**
- `profile.name`, `profile.avatar`, `profile.socials`
- `experience[].company`, `.startDate`, `.endDate`, `.location`, `.logo`
- `education.*` (all fields)
- `projects[].title`, `.image`, `.liveUrl`, `.status`
- `contact.email`, `.phone`

## Relevance Rating

Before tailoring, rate the JD on a 1–10 scale:

| Score | Meaning |
|---|---|
| 9–10 | Perfect match — most skills already in data |
| 7–8 | Strong match — minor rephrasing |
| 5–6 | Moderate match — some gaps |
| 3–4 | Weak match — significant gaps |
| 1–2 | Poor match — mostly different skills |

If rating ≤ 3, ask user whether to proceed.

## Anti-Slop Rules

Never produce:
- "Collaborated with cross-functional teams"
- "Drove strategic initiatives"
- "Leveraged cutting-edge solutions"
- "Played a key role in"

Always use the quantification format:
```
[Action Verb] + [What] + [How/Why] + [Result/Impact]
```

Example: "Optimized Django queries using select_related/prefetch_related, reducing page load time by 40%"

## Related Pages

- [[system]] — overall architecture
- [[experience]] — the data being tailored
