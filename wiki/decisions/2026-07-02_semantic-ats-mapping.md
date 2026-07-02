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
  - `build_keyword_matrix()` performs deterministic diff-based keyword traceability
  - `tone` parameter flows through pipeline: `server.py` → `run_pipeline()` → `tailor_all_sections()` → individual `tailor_*()` functions
  - Frontend: tone selector added to both tailoring and cover letter sections
