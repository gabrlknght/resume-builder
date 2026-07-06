---
title: Project Overview
type: overview
last_updated: 2026-07-06
sources: [AGENTS.md, customizer/TAILOR_SKILL.md]
---

# Resume Builder — Project Overview

## What It Is

A personal resume generation and AI-tailoring system built by Avik Nandy. It stores resume content as structured JSON and compiles it into a professional LaTeX PDF — either automatically via CI/CD or on-demand via a local web UI.

The project has two modes of use:

1. **Zero-setup CI/CD**: Push changes to `data/*.json` on GitHub → GitHub Actions generates and publishes the PDF automatically.
2. **Local power-user UI**: Run the FastAPI web server (`customizer/server.py`), edit JSON visually, preview PDF in real time, and run AI tailoring against job descriptions.

## Core Data Flow

```
data/*.json  →  templates/resume.tex.j2  →  resume.tex  →  pdflatex  →  resume.pdf
```

The JSON files are the single source of truth. The LaTeX template (Jinja2) injects them. The CI/CD and local scripts both use the same rendering path.

## AI Tailoring

The `/api/tailor` endpoint accepts a job description and runs a 5-stage LLM pipeline (JD Analysis, Match & Score, Section Tailoring, Keyword Mapping, Validation) to rewrite resume sections. See [[pipeline]] for detail. Key design choices:
- Structured output via `instructor` (Pydantic validation + auto-retry)
- BYOK: user supplies their own API key and model (OpenAI, Gemini, Cerebras, OpenRouter)
- SSE progress streaming so the UI shows stage-by-stage updates, not a spinner
- Immutable field protection: company names, dates, URLs are restored if the LLM mutates them

## The Owner

**Avik Nandy** — Enterprise WordPress engineer, 8+ years. Owner of Harbinger Industries (Alexandria, VA). Also a designer and long-time contractor. Specializes in PHP/JavaScript, WordPress enterprise, CI/CD, and increasingly AI-first workflows. See [[profile]] and [[experience]].

## Design Philosophy

- Brutalist, developer-centric UI (JetBrains Mono, black-and-white)
- Never add fabricated achievements — only rephrase real ones
- Secure by default: immutable field protection, BYOK, local-first option (Ollama)
- The `data/*.json` schema cleanly separates content from presentation

## Related Pages

- [[system]] — tech stack and architecture detail
- [[pipeline]] — 5-stage tailoring pipeline
- [[profile]] — current resume profile
- [[experience]] — full work history
