---
title: AI Tailoring Pipeline
type: architecture
last_updated: 2026-07-02
sources: [AGENTS.md, customizer/pipeline.py, customizer/TAILOR_SKILL.md]
---

# AI Tailoring Pipeline

The `/api/tailor` endpoint implements a 5-stage pipeline (originally 4, now includes Stage 3.5: Keyword Mapping) that replaces the original single-prompt approach. Each stage has a focused responsibility and dedicated cost profile.

## Stages

```
Stage 1: JD Analysis       — Extracts structured requirements from JD text
                             LLM call, temperature=0.1
                             Outputs: JDAnalysis model (keywords, semantic concepts, tone cues)
Stage 2: Match & Score     — Deterministic keyword matching, no LLM cost
                             Early exit if relevance ≤ 2
Stage 3: Section Tailoring — 3 parallel LLM calls via asyncio.gather
                             (profile, experience, projects)
Stage 3.5: Keyword Mapping — Deterministic diff-based keyword traceability
                             NEW (2026-07-02): produces mapping matrix
Stage 4: Validate & Assemble — Pydantic validation + immutable field checks + eval metrics
                             + injects keyword_mapping into final output
```

## Key Design Choices

**Semantic ATS Mapping** — (Added 2026-07-02) The pipeline now extracts semantic concepts and tone cues from JD analysis (Stage 1), and uses them throughout Stage 3 to produce more natural, contextually-aware resume rewrites. Keywords are embedded with attention to thematic alignment, not just string matching.

**Unified rewriting strategy** — (Updated 2026-07-02) Stage 3 replaces three disjointed section prompts with a shared `STAGE3_REWRITE_STRATEGY` that enforces consistent semantic mapping, preservation rules, and honesty constraints across profile, experience, and projects.

**Keyword Mapping Matrix** — (Added 2026-07-02) Stage 3.5 deterministically diffs original vs. tailored bullets and traces where each JD keyword landed in the rewritten resume. This provides auditability — users can verify the LLM actually embedded the requested keywords.

**Tone control** — (Added 2026-07-02) Users select tone (Professional, Formal, Innovative, Collaborative, Technical, Conversational) from the UI. The tone is injected into all Stage 3 prompts, ensuring the rewritten resume matches the desired register.

**Structured output via `instructor`** — Pydantic models define expected LLM output shape. `instructor` handles automatic retry on validation failures. No manual JSON parsing.

**BYOK (Bring Your Own Key)** — User selects provider (OpenAI, Gemini, Cerebras, OpenRouter), model, and API key via UI. The pipeline adapts to the chosen provider.

**SSE progress streaming** — Each stage emits a Server-Sent Event when it completes. The UI updates a progress bar stage-by-stage. No opaque spinner.

**Immutable field protection** — After Stage 3, Stage 4 auto-restores any LLM-mutated immutable fields:
- Company names
- Dates (startDate, endDate)
- Locations
- URLs (liveUrl, socials, etc.)

**Parallel tailoring** — Stage 3 runs three LLM calls concurrently (`asyncio.gather`) for profile, experience, and projects. All three calls share the same rewriting strategy template with injected context (tone, semantic concepts, must-have keywords). Reduces latency vs. sequential calls.

**Eval metrics** — Stage 4 computes:
- `job_alignment_score` — how well tailored output matches JD keywords
- `content_preservation` — how much original content was kept
- `hallucinated_numbers` — detected fabricated metrics (should be 0)
- **keyword_mapping** — (Added 2026-07-02) deterministic traceability table injected into final output by Stage 3.5

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

If rating ≤ 2, pipeline auto-exits without tailoring (early-out).

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
