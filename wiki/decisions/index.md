---
title: Decisions Log
type: synthesis
last_updated: 2026-06-28
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
