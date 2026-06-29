# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Start the local server:**
```bash
uv run python customizer/server.py
# or with custom host/port:
uv run uvicorn customizer.server:app --host 0.0.0.0 --port 8080 --reload
```

**Build frontend assets** (required after editing `app.js` or `style.css`):
```bash
npm run build          # minifies JS + CSS
npm run build:js       # JS only
npm run build:css      # CSS only
```
The server serves `app.min.js` and `style.min.css` — always rebuild after frontend edits, then hard-refresh (Ctrl+Shift+R).

**Lint:**
```bash
npm run lint           # runs eslint + stylelint + ruff
ruff check .           # Python only
npm run lint:js        # JS only
npm run lint:css       # CSS only
```

**Render resume manually (no UI):**
```bash
python3 scripts/render_resume.py
pdflatex -interaction=nonstopmode resume.tex
pdftotext resume.pdf resume.txt   # ATS plain-text fallback
```

**Install all dependencies:**
```bash
bash install.sh
```

## Architecture

### Core data flow
```
data/*.json  →  templates/resume.tex.j2  →  resume.tex  →  pdflatex  →  resume.pdf
```
`data/*.json` is the single source of truth. The Jinja2 LaTeX template injects it. Both CI/CD and the local server use the same rendering path (`scripts/render_resume.py`).

### Backend (`customizer/`)
- **`server.py`** — FastAPI + Uvicorn entry point; serves the web UI and all API routes
- **`server_additions.py`** — Additional route handlers (history, stats, skills CRUD)
- **`pipeline.py`** — 4-stage AI tailoring pipeline (see below)
- **`config.py`** — Settings and environment variable config (`<PROVIDER>_API_KEY` env vars)
- **`data_utils.py`** — JSON read/write helpers for `data/*.json`
- **`history_manager.py`** — Resume and cover letter history tracking (`data/history/`, `data/cl-history/`)
- **`pdf_generator.py`** — Wrapper around `pdflatex` invocation

### Frontend (`customizer/static/`)
Vanilla JS (ES6+), no framework. Design system: brutalist black-and-white, JetBrains Mono.
- **`app.js`** — Main entry point (edit this, not `app.min.js`)
- **`state.js`** — Frontend state management
- **`api-utils.js`** — Fetch wrappers for backend API calls
- **`dom-utils.js`** — DOM manipulation helpers
- **`form-utils.js`** — Form population and collection

PDF preview uses Mozilla `pdf.js` embedded in the browser.

### AI Tailoring Pipeline (`customizer/pipeline.py`)
Four stages, each with a distinct cost and responsibility:

| Stage | What it does | LLM? |
|---|---|---|
| 1: JD Analysis | Extracts structured requirements from job description text | Yes (temp=0.1) |
| 2: Match & Score | Deterministic keyword matching; early exit if relevance ≤ 2 | No |
| 3: Section Tailoring | 3 parallel LLM calls via `asyncio.gather` (profile, experience, projects) | Yes |
| 4: Validate & Assemble | Pydantic validation + immutable field restoration + eval metrics | No |

Uses `instructor` library for structured output with automatic retry on Pydantic validation failures. Streams stage-by-stage progress to the browser via Server-Sent Events (SSE).

**Immutable fields** auto-restored in Stage 4 if LLM mutates them: company names, dates, locations, URLs.

**Eval metrics** computed in Stage 4: `job_alignment_score`, `content_preservation`, `hallucinated_numbers`.

### CI/CD
`.github/workflows/build-resume.yml` triggers on changes to `data/*.json`, `templates/`, or `scripts/`. Installs Python+Jinja2 → renders LaTeX → compiles via `xu-cheng/latex-action` → creates/updates "latest" GitHub Release with PDF.

## Wiki (Knowledge Base)

A persistent LLM-maintained wiki lives at `wiki/`. **Read `wiki/index.md` first** before answering questions about this project — it catalogs all pages. The wiki accumulates knowledge across sessions so it doesn't need to be re-derived each time.

Key files:
- `wiki/SCHEMA.md` — Operating manual: operations (Ingest, Query, Update, Lint), page formats, rules
- `wiki/index.md` — Page catalog; always read first when querying
- `wiki/log.md` — Append-only activity log (grep: `grep "^## \[" wiki/log.md | tail -10`)
- `wiki/decisions/` — ADRs: architectural and project decisions with rationale
- `wiki/applications/` — One page per job tailoring session

**Wiki sync rule:** `data/*.json` is the sole source of truth for resume content and is not mirrored in the wiki. When a decision or architecture change happens, add/update an ADR in `wiki/decisions/` and append to `wiki/log.md`.

**Log entry format:** `## [YYYY-MM-DD] <type> | <short title>` — types: `ingest`, `query`, `update`, `lint`, `application`, `decision`

**Application pages** go in `wiki/applications/YYYY-MM-DD_company_role.md` and are never deleted.

## Edit Protocol

- Read a file before editing it
- Make only one logical change per tool call — never batch multiple edits
- After each edit, re-read the file to verify it looks correct before continuing
- If an edit produces unexpected output, stop and report — do not attempt to self-correct more than once

## JSON File Rules

Always write JSON via Python, never with heredocs or the Write tool directly:
```bash
python3 -c "import json; data = {...}; open('file.json','w').write(json.dumps(data, indent=2))"
```

## Hard Stop Rules

- If a file write or edit fails twice, **stop completely**
- Do not attempt a third approach
- Output the intended file contents as a code block in chat and wait for user instruction

## Tailoring Rules

**Can be changed:** `profile.title`, `profile.bio`, `experience[].role`, `experience[].details[]`, `projects[].description`, `projects[].technologies[]`, `contact.availability`

**Never changed:** `profile.name`, `profile.avatar`, `profile.socials`, `experience[].company`, `.startDate`, `.endDate`, `.location`, `.logo`, all `education.*` fields, `projects[].title`, `.image`, `.liveUrl`, `.status`, `contact.email`, `.phone`

**Anti-slop:** Never write "collaborated with cross-functional teams", "drove strategic initiatives", "leveraged cutting-edge solutions", "played a key role in". Use the quantification format: `[Action Verb] + [What] + [How/Why] + [Result/Impact]`.

**Relevance rating:** Rate any JD 1–10 before tailoring. If ≤ 3, ask the user whether to proceed.

## Python Linting Config

- Target: Python 3.12, line length 100
- `ruff` selects E, F, W, I rules; ignores E501
- `customizer/server.py` ignores E402 (sys.path set before imports by design)
