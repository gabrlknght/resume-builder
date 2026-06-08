# AI Agent Integration Details

This project leverages both automated CI/CD and AI-assisted workflows to build, maintain, and customize professional resumes from structured JSON data.

## Two Workflows

- **CI/CD (Zero Setup)**: Push JSON changes to GitHub → PDF auto-generated via GitHub Actions. No local installation required.
- **Local Web UI (Power User)**: Run `bash install.sh` to set up all dependencies, then `customizer/server.py` → Edit JSON visually, preview PDF in real-time, generate on-demand with full local control.

## Core Architecture

- **JSON Data Structure**: The `data/*.json` schema (profile, experience, education, projects, skills, contact) cleanly separates content from presentation.
- **LaTeX Templates**: `templates/resume.tex.j2` uses Jinja2 templating to inject JSON data into a professional LaTeX document.
- **Build Scripts**: `scripts/render_resume.py` parses templates, loads data, and generates `.tex` output.
- **Tailoring Pipeline**: `customizer/pipeline.py` implements the 4-stage AI tailoring pipeline using `instructor` for structured LLM output.

## Local Web UI (customizer/)

The built-in web interface for power users who want local control:

- **Stack**: FastAPI + Uvicorn (backend), Jinja2 (templating), Vanilla JavaScript (frontend).
- **Design System**: Minimalist black-and-white with JetBrains Mono font (brutalist, developer-centric).
- **PDF Preview**: Real-time preview via Mozilla's `pdf.js` embedded in browser.
- **Data Persistence**: Reads from/writes to `data/*.json` files via "Save to Backend" button.
- **Real-Time AI Progress**: Tailoring streams stage-by-stage progress via SSE (Server-Sent Events) — JD Analysis, Match & Score, Section Tailoring, Validation.

## The `tailor-resume` AI Skill

This repository is designed to be highly interoperable with AI coding assistants. Use the **`resume-builder-tailor`** AI skill to adapt your resume for specific job descriptions.

- **Skill Location**: https://github.com/jangwanAnkit/skills/tree/main/resume-builder-tailor
- **How it works**: An AI agent equipped with this skill reads `data/*.json` files, analyzes a job description, and rewrites bullet points, skills, and summary to match the target role.
- **Usage**: Ask your AI assistant to "tailor resume to [Job Description]" — it will safely update the JSON structure.

### Built-in Web Integration (Multi-Stage Pipeline)

The `/api/tailor` endpoint uses a **4-stage pipeline** that replaces the original single-prompt approach. Each stage has a focused responsibility:

```
Stage 1: JD Analysis      — Extracts structured requirements from JD text (LLM, temperature=0.1)
Stage 2: Match & Score    — Deterministic keyword matching, no LLM cost. Early exit if relevance ≤ 2
Stage 3: Section Tailoring — 3 parallel LLM calls (profile, experience, projects) via asyncio.gather
Stage 4: Validate & Assemble — Pydantic schema validation + immutable field checks + eval metrics
```

- **Structured Output**: Uses the `instructor` library for automatic Pydantic validation and retry on LLM output failures.
- **BYOK Support**: Users specify provider (OpenAI, Gemini, Cerebras, OpenRouter), API Key, and Model via the UI.
- **SSE Progress Streaming**: Real-time stage-by-stage progress updates via Server-Sent Events (not a blind spinner).
- **Eval Metrics**: Each tailoring run computes `job_alignment_score`, `content_preservation`, and `hallucinated_numbers` from the `eval-module`.
- **Immutable Field Protection**: Company names, dates, locations, and URLs are auto-restored if the LLM mutates them.
- **Dynamic Diffing**: The UI renders a visual diff in the Preview pane after tailoring completes.
- **JD Match Scoring**: Relevance score (1-10) with gap analysis showing matched vs missing requirements.

**Pipeline code**: `customizer/pipeline.py` — all stage functions, Pydantic models, and the SSE orchestrator.
**Eval module**: `eval-module/eval/` — schemas, metrics, golden test cases (used by Stage 4 for validation).

## CI/CD Workflow

GitHub Actions (`.github/workflows/build-resume.yml`) auto-generates PDFs on every push to `main`:

1. Triggers on changes to `data/*.json`, `templates/`, or `scripts/`
2. Installs Python + Jinja2
3. Runs `scripts/render_resume.py` to generate LaTeX
4. Compiles LaTeX to PDF via `xu-cheng/latex-action`
5. Creates/updates a "latest" release with the PDF

## Edit Protocol
- Before editing any file, read its current contents first
- Make only one logical change per tool call — never batch multiple edits
- After each edit, re-read the file to verify it looks correct before continuing
- If an edit produces unexpected output, stop and report — do not attempt to self-correct more than once
- Never attempt to fix a broken edit by making another edit — ask the user instead

## File Writing Rules
- When writing or modifying JSON files, always use Python via bash:
  python3 -c "import json; data = {...}; open('file.json','w').write(json.dumps(data, indent=2))"
- Never use bash heredocs for JSON — they corrupt nesting and brackets
- Never use the write tool for JSON files
- For any other file type, prefer the write tool over heredocs

## Hard Stop Rules
- If a file write or edit fails twice, STOP COMPLETELY
- Do not attempt a third approach
- Output the intended file contents as a code block in chat and wait for user instruction
- Never narrate your own failure — report it once, then stop
