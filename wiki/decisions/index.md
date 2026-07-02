---
title: Decisions Log
type: synthesis
last_updated: 2026-07-02
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
- **Decision:** Split tailoring into 4 stages: (1) JD Analysis, (2) Match & Score, (3) Section Tailoring, (4) Validate & Assemble.
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
- **Status:** Accepted
- **Context:** The original pipeline used keyword-level matching (Stage 2) and simple keyword injection (Stage 3). This produced resumes that mentioned JD terms but often read unnaturally — the semantic intent behind requirements (e.g., "cross-functional leadership" vs. just "led team") was lost. Users also had no control over resume tone and no way to verify which keywords the LLM actually embedded.
- **Decision:** Implement a Semantic ATS Mapping framework that extends Stage 1 to extract semantic concepts and tone cues, replaces three disjointed Stage 3 prompts with a unified rewriting strategy, adds a deterministic Stage 3.5 keyword mapping matrix, and adds a tone parameter to all LLM prompts.
- **Consequences:**
  - + Semantic concepts capture thematic intent, not just string matches
  - + Unified strategy ensures consistent rewriting ethos across sections
  - + Keyword mapping matrix provides auditability
  - + Tone control lets users match the desired register
  - - More LLM output per tailoring session (semantic_concepts + tone_cues)
  - - Stage 3.5 adds ~200ms deterministic computation (negligible)
  - - Semantic concepts are free-form text from the LLM; quality depends on Stage 1 prompt
