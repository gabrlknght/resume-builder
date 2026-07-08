---
title: Decisions Log
type: synthesis
last_updated: 2026-07-07
sources: []
---

# Decisions Log

Recorded architectural and project decisions with rationale.

> This file is the entry point for all project decisions. New entries should be added as separate files under `decisions/YYYY-MM-DD_short-title.md` and cross-linked here.

## ADR-001: Flat JSON Files Over Database

- **Date:** 2026-06-16
- **Status:** Accepted
- **Context:** The resume data is small (~10KB), static, and version-controlled. A database would add operational overhead (setup, migration, backups) for zero benefit.
- **Decision:** Use flat JSON files in `data/` as the single source of truth.
- **Consequences:**
  - + Simple to read, write, diff, and version-control
  - + Works with any tool that can parse JSON
  - - No query language or indexing — fine for <100 records
  - - Concurrency contention if multiple writers edit the same file simultaneously

## ADR-002: Jinja2 for LaTeX Templating

- **Date:** 2026-06-16
- **Status:** Accepted
- **Context:** Need to inject structured JSON data into a LaTeX document. Must separate content from presentation.
- **Decision:** Use Jinja2 as the templating engine for `templates/resume.tex.j2`.
- **Consequences:**
  - + Jinja2 is already in the dependency list
  - + Python-native, no extra tooling
  - + Supports conditionals, loops, filters — enough for resume layout
  - - Not a full HTML engine — CSS-in-LaTeX is the only styling path

## ADR-003: 4-Stage Tailoring Pipeline Over Single Prompt

- **Date:** 2026-06-16
- **Status:** Accepted
- **Context:** A single LLM prompt to "tailor this resume to the JD" is cheap but produces hallucinated numbers, mutated immutable fields, and no diagnostic output.
- **Decision:** Split tailoring into 4 stages: (1) JD Analysis, (2) Match & Score, (3) Section Tailoring, (4) Validate & Assemble. (Later: Stage 3.5 — Keyword Mapping — was added in 2026-07-02, see ADR-007.)
- **Consequences:**
  - + Stage 2 is free (deterministic, no LLM cost)
  - + Stage 4 catches hallucinations and restores immutable fields
  - + SSE streaming gives users visibility into progress
  - - More LLM calls per tailoring session (Stage 3 = 3 parallel calls)
  - - More complex error handling (each stage can fail independently)

## ADR-004: BYOK Over Built-in API Keys

- **Date:** 2026-06-16
- **Status:** Accepted
- **Context:** Shipping a public-facing tool with embedded API keys is a security risk and a cost liability.
- **Decision:** Users supply their own API key and model via the UI.
- **Consequences:**
  - + No API key leakage risk
  - + Users pay for their own LLM usage
  - + Supports any provider (OpenAI, Gemini, Cerebras, OpenRouter)
  - - Higher onboarding friction (users must find and paste a key)

## ADR-005: Minified Assets Served by Default

- **Date:** 2026-06-16
- **Status:** Accepted
- **Context:** The web UI serves JS and CSS. Development needs sourcemaps and readable code; production needs small payloads.
- **Decision:** Serve `app.min.js` and `style.min.css` by default. Developers run `npm run build` to regenerate.
- **Consequences:**
  - + Smaller payload, faster page load
  - - Debugging in browser DevTools requires hard-refresh + source maps
  - - Developers must remember to rebuild after edits

## ADR-006: llama.cpp as a Local Provider with Reasoning Disable + Output Token Cap

- **Date:** 2026-06-29
- **Status:** Accepted
- **Context:** User moved to an AMD machine and needed local LLM inference via llama.cpp. Reasoning-capable models (e.g. Qwen3.x) burn thousands of tokens on hidden `<think>` chains before emitting the JSON `instructor` waits for. Small/local models on memory-bandwidth-bound hardware have no incentive to stop generating — a runaway call can take a minute+.
- **Decision:** Added `llamacpp` as a first-class provider with default URL `localhost:8080/v1`, no API key required, disabled reasoning chains via `chat_template_kwargs`, and a 2048-token hard ceiling on all pipeline LLM calls.
- **Consequences:**
  - + Fast results on non-CUDA, memory-bandwidth-bound hardware
  - + Hidden reasoning chains cut out — smaller outputs, faster decode
  - + Output token cap prevents runaway generations
  - - llama.cpp must be running separately on port 8080
  - - User must load a compatible model into llama.cpp manually

## ADR-007: Semantic ATS Mapping Framework

- **Date:** 2026-07-02
- **Status:** Accepted — Amended 2026-07-02 (post-review fixes; full amendment log below)
- **Context:** The original pipeline used keyword-level matching (Stage 2) and simple keyword injection (Stage 3). This produced resumes that mentioned JD terms but often read unnaturally — the semantic intent behind requirements (e.g., "cross-functional leadership" vs. just "led team") was lost. Users also had no control over resume tone and no way to verify which keywords the LLM actually embedded.
- **Decision:** Implement a Semantic ATS Mapping framework that extends Stage 1 to extract semantic concepts and tone cues, replaces three disjointed Stage 3 prompts with a unified rewriting strategy (with section-specific addenda), adds a deterministic Stage 3.5 keyword mapping matrix, and adds a tone parameter to all LLM prompts including cover letters.
- **Consequences:**
  - + Semantic concepts capture thematic intent, not just string matches
  - + Section-specific strategy addenda restore precision lost in consolidation
  - + Keyword mapping matrix provides auditability (position-independent, all keywords per bullet recorded)
  - + Tone control works for both resume tailoring and cover letter generation
  - + `tone_cues` from Stage 1 now feed into Stage 3 as supplemental context
  - - More LLM output per tailoring session (semantic_concepts + tone_cues)
  - - Stage 3.5 adds ~200ms deterministic computation (negligible)
  - - Semantic concepts are free-form text from the LLM; quality depends on Stage 1 prompt

### Amendments — 2026-07-02 (code review)

A senior code review identified and fixed the following bugs and design gaps in the initial implementation:

**[P0] Cover letter tone silently dropped**
`run_cover_letter_pipeline()` accepted `tone` and passed it only to SSE response metadata. It was never forwarded to `generate_cover_letter()`, which had no `tone` parameter. The cover letter tone UI selector had zero effect on the actual LLM prompt.
Fix: added `tone: str = "professional"` to `generate_cover_letter()`, converted `COVER_LETTER_SYSTEM` to a format string with a `{tone}` placeholder (with `{{...}}` escaped braces in examples), and forwarded `tone` through the call chain.

**[P0] `build_keyword_matrix` missed multi-keyword bullets**
The inner keyword loop contained a `break` after the first keyword match per bullet, meaning a bullet containing both "Python" and "machine learning" would only record the first match. All subsequent keywords in the same bullet were silently dropped.
Fix: removed `break`; the existing deduplication set at the end of the function handles `(keyword, new_position)` uniqueness.

**[P1] Positional diff invalidated by bullet reordering**
`_diff_bullets()` matched bullets by index. Stage 3 prompts explicitly allow reordering bullets ("lead with most relevant achievements"). If the LLM reordered bullets 1 and 2, the diff would pair them cross-wise, producing incorrect "original → tailored" attributions in the matrix.
Fix: removed `_diff_bullets()` entirely. `build_keyword_matrix()` now iterates all tailored bullets directly and pairs each with the original at the same position as best-effort context — no ordering assumption, no false attributions.

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

## ADR-009: Theme Fonts + Color Settings

- **Date:** 2026-07-07
- **Status:** Accepted
- **Context:** The web UI had a single color scheme (black and white) and a single font (JetBrains Mono). Users wanted personalization — the ability to customize the look and feel without forking the codebase.
- **Decision:** Added a theme modal with 5 color schemes (Default, Darkslime, Crimson, Ocean, Sunset) and 4 Google Fonts (JetBrains Mono, IBM Plex Mono, Inter, Space Mono). Theme and font selections are persisted in `localStorage` and applied via CSS custom properties and dynamic font loading.
- **Consequences:**
  - + Users can personalize the UI without forking
  - + Theme/font choices persist across sessions via `localStorage`
  - + CSS custom properties (`--bg`, `--text`, `--accent`, `--secondary`, `--border`, `--font-main`, `--font-mono`) make theming trivial to extend
  - - Google Fonts loading adds external HTTP requests (4 font families × 2 weights each = 8 font files)
  - - The `#000000` theme-color meta tag was removed and replaced with dynamic CSS — browser UI elements (tab bar, status bar) no longer match the page theme

## ADR-008: Generation Metrics Tracking (Tokens/Time)

- **Date:** 2026-07-02
- **Status:** Accepted
- **Context:** Users running local providers (llama.cpp/Ollama) had no visibility into token counts, elapsed time, or throughput per generation.
- **Decision:** Added a `MetricsTracker` wrapping every LLM call to sum completion tokens and wall-clock elapsed time, surfaced through history tables, both preview panes, and a dual-axis "Avg tok/s" line on the Stats chart. Also raised the `llamacpp` client timeout 120s → 600s after discovering Stage 3's concurrent calls queue behind each other on single-slot local servers. See [[2026-07-02_generation-metrics-tracking]] for full detail.
- **Consequences:**
  - + Per-generation throughput and duration visible across tables, previews, and a trend chart
  - + Metrics degrade gracefully for pre-existing history (no `timing` key)
  - + Timeout fix reduces spurious Stage 3 failures for local providers
  - - Token counts depend on the provider populating a `usage` block; not guaranteed for all OpenAI-compatible local servers
  - - Stage 3 still fires concurrently against local providers — the timeout bump papers over queuing rather than avoiding it
