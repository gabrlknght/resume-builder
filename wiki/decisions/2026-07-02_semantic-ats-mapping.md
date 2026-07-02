---
title: Semantic ATS Mapping Framework
type: decision
date: 2026-07-02
status: Accepted
sources: [Semantic-ATS-Mapping.md, customizer/pipeline.py, customizer/server.py, customizer/static/app.js, customizer/templates/index.html]
---

# ADR-007: Semantic ATS Mapping Framework

- **Date:** 2026-07-02
- **Status:** Accepted
- **Context:** The original pipeline used keyword-level matching (Stage 2) and simple keyword injection (Stage 3). This produced resumes that mentioned JD terms but often read unnaturally — the semantic intent behind requirements (e.g., "cross-functional leadership" vs. just "led team") was lost. Users also had no control over resume tone and no way to verify which keywords the LLM actually embedded.

- **Decision:** Implement a Semantic ATS Mapping framework that:
  1. Extends Stage 1 (JD Analysis) to extract **semantic concepts** and **tone cues** beyond raw keywords
  2. Replaces three disjointed Stage 3 prompts with a **unified rewriting strategy** that injects semantic context
  3. Adds a deterministic **Stage 3.5: Keyword Mapping Matrix** that traces where each JD keyword landed in the tailored resume
  4. Adds a **tone parameter** (Professional, Formal, Innovative, Collaborative, Technical, Conversational) to all LLM prompts

- **Consequences:**
  - + Semantic concepts capture thematic intent, not just string matches (e.g., "data-driven decision making" covers "used analytics to inform strategy")
  - + Unified strategy ensures consistent rewriting ethos across profile, experience, and projects sections
  - + Keyword mapping matrix provides auditability — users can verify the LLM embedded requested keywords
  - + Tone control lets users match the desired register (formal for corporate roles, conversational for startups)
  - - More LLM output per tailoring session (Stage 1 produces semantic_concepts + tone_cues fields)
  - - Stage 3.5 adds ~200ms deterministic computation (negligible)
  - - Semantic concepts are free-form text from the LLM; quality depends on Stage 1 prompt

- **Rejected alternatives:**
  - **LLM-generated mapping matrix (Option A):** Considered having the LLM produce the keyword mapping in Stage 3.5. Rejected because deterministic diff-based mapping is zero-cost, deterministic, and avoids another LLM call.
  - **Separate semantic matching model (Stage 2b):** Considered adding a semantic similarity scorer (e.g., sentence embeddings) to Stage 2. Rejected because the primary goal is improving rewrite quality, not scoring accuracy. Semantic concepts feed into Stage 3 rewrites, not Stage 2 scoring.

- **Implementation details:**
  - `JDAnalysis` model extended with `semantic_concepts: list[str]` and `tone_cues: str`
  - `STAGE1_SYSTEM` prompt updated to request semantic concepts and tone cues
  - `STAGE3_REWRITE_STRATEGY` replaces `STAGE3_PROFILE_SYSTEM`, `STAGE3_EXPERIENCE_SYSTEM`, `STAGE3_PROJECTS_SYSTEM`
  - `_tailor_context()` helper builds context dict for all Stage 3 calls
  - `build_keyword_matrix()` performs deterministic keyword traceability
  - `tone` parameter flows through pipeline: `server.py` → `run_pipeline()` → `tailor_all_sections()` → individual `tailor_*()` functions
  - Frontend: tone selector added to both tailoring and cover letter sections

---

## Amendments — 2026-07-02 (code review)

A senior code review identified and fixed the following bugs and design gaps in the initial implementation:

### Bugs fixed

**[P0] Cover letter tone silently dropped**
`run_cover_letter_pipeline()` accepted `tone` and passed it only to SSE response metadata. It was never forwarded to `generate_cover_letter()`, which had no `tone` parameter. The cover letter tone UI selector had zero effect on the actual LLM prompt.
Fix: added `tone: str = "professional"` to `generate_cover_letter()`, converted `COVER_LETTER_SYSTEM` to a format string with a `{tone}` placeholder (with `{{...}}` escaped braces in examples), and forwarded `tone` through the call chain.

**[P0] `build_keyword_matrix` missed multi-keyword bullets**
The inner keyword loop contained a `break` after the first keyword match per bullet, meaning a bullet containing both "Python" and "machine learning" would only record the first match. All subsequent keywords in the same bullet were silently dropped.
Fix: removed `break`; the existing deduplication set at the end of the function handles `(keyword, new_position)` uniqueness.

**[P1] Positional diff invalidated by bullet reordering**
`_diff_bullets()` matched bullets by index. Stage 3 prompts explicitly allow reordering bullets ("lead with most relevant achievements"). If the LLM reordered bullets 1 and 2, the diff would pair them cross-wise, producing incorrect "original → tailored" attributions in the matrix.
Fix: removed `_diff_bullets()` entirely. `build_keyword_matrix()` now iterates all tailored bullets directly and pairs each with the original at the same position as best-effort context — no ordering assumption, no false attributions.

### Design improvements applied

**[P1] Section-specific strategy addenda restored**
The initial consolidation into `STAGE3_REWRITE_STRATEGY` removed section-specific rules that were in the original three prompts. Profile got an addendum (`STAGE3_PROFILE_STRATEGY`) but experience and projects did not.
Fix: added `STAGE3_EXPERIENCE_STRATEGY` (bullets may be reordered, quantification format enforced) and `STAGE3_PROJECTS_STRATEGY` (tech list reordering allowed but no additions, strict field preservation). Each extends the shared base.

**[P2] `tone_cues` now wired into Stage 3**
`JDAnalysis.tone_cues` was extracted by Stage 1 but discarded — Stage 3 only received the user-selected dropdown value. The LLM-observed tone signals from the JD were paid for but never used.
Fix: `_tailor_context()` now includes `tone_cues`; each `tailor_*()` user message conditionally appends `JD tone cues: ...` so the LLM has both the explicit user preference and the JD's observed language register.

**[P2] Redundant tone removed from user messages**
`tone` appeared in both the system prompt (`Tone: {tone}` in `STAGE3_REWRITE_STRATEGY`) and every `tailor_*()` user message (`f"Tone: {tone}\n\n"`). The user message duplication was noisy.
Fix: removed `f"Tone: {tone}\n\n"` from all three user messages; tone is now injected once via the system prompt only.

**[P3] `_tailor_context` return type annotation corrected**
Function was annotated `-> str` but returned `dict`.

**[P3] `Semantic-ATS-Mapping.md` broken template variable**
`{{resume_text}}` was split across two lines as `{{resume_\ntext}}` — a copy-paste artifact.
