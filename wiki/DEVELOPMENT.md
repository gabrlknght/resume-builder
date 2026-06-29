---
title: Development Guide
type: synthesis
last_updated: 2026-06-28
sources: [AGENTS.md, CLAUDE.md, customizer/server.py, customizer/pipeline.py]
---

# Development Guide

Setup instructions, common pitfalls, and local UI troubleshooting.

## Quick Start

```bash
# 1. Install frontend deps
npm install

# 2. Build minified assets
npm run build

# 3. Install Python deps
pip install jinja2 fastapi uvicorn instructor

# 4. Start the local server
python customizer/server.py
# or
uv run uvicorn customizer.server:app --host 0.0.0.0 --port 8080 --reload
```

The web UI opens at `http://localhost:8000` (or whichever port `server.py` binds to).

## Frontend Development

After editing `app.js` or `style.css`:

```bash
npm run build   # minifies both JS and CSS
```

Then hard-refresh in the browser (**Ctrl+Shift+R** or **Cmd+Shift+R**). The server serves the `.min.*` files by default.

### Build Commands

| Command | What it does |
|---|---|
| `npm run build` | Minify JS + CSS |
| `npm run build:js` | JS only |
| `npm run build:css` | CSS only |

### File Map

| File | Purpose |
|---|---|
| `app.js` | Main app logic (source) |
| `app.min.js` | Minified (served) |
| `api-utils.js` | API call helpers |
| `dom-utils.js` | DOM manipulation |
| `form-utils.js` | Form handling |
| `state.js` | Frontend state management |
| `style.css` | Styles (source) |
| `style.min.css` | Minified (served) |

## Local PDF Generation

```bash
# Render LaTeX from JSON
python scripts/render_resume.py

# Compile to PDF (requires pdflatex)
pdflatex resume.tex
# or
make pdf
```

### Troubleshooting pdflatex

| Symptom | Fix |
|---|---|
| `pdflatex: command not found` | Install TeX Live: `sudo apt install texlive-latex-base texlive-fonts-recommended texlive-fonts-extra texlive-latex-recommended` |
| `! Undefined control sequence` | Check the `.log` file for the exact line number; usually a missing LaTeX package or typo in the template |
| `Package inputenc Error` | Add `\usepackage[utf8]{inputenc}` to the template preamble if non-ASCII characters appear |

## AI Tailoring Development

The tailoring pipeline lives in `customizer/pipeline.py`. Key entry points:

```
POST /api/tailor
  Body: { "jobDescription": "..." }
  Streams: SSE events for stage progress
  Response: Tailored JSON + diff + eval metrics
```

### Adding a New LLM Provider

1. Add provider config to `customizer/config.py` (API URL, default model, header format)
2. Update `pipeline.py`'s LLM client to handle the new provider's message format
3. Add the provider to the UI's dropdown (search for `provider` in `static/`)

### Debugging Pipeline Stages

Each stage emits an SSE event:

```
event: stage_start
data: {"stage": 1, "name": "JD Analysis"}

event: stage_progress
data: {"stage": 1, "status": "parsing", "detail": "extracted 12 keywords"}

event: stage_complete
data: {"stage": 1, "result": {...}}
```

Watch events in the browser DevTools → Network → SSE connection.

## Wiki Maintenance

### Lint Wiki Health

```bash
make wiki-lint
```

Checks:
- Stale `last_updated` dates (>30 days)
- Orphan pages (no inlinks from index or other pages)
- Expected directories (`decisions/`, `applications/`) exist

This runs in CI on every push touching `wiki/` or `scripts/wiki_lint.py`, but it's a warning only — it does not block the resume PDF build.

### Resume Content

`data/*.json` is the sole source of truth for resume content and is not mirrored into the wiki. `make wiki-sync` is just a reminder of this — see `wiki/SCHEMA.md`.

### Create a New Wiki Page

```bash
mkdir -p wiki/<directory>
# Write the page with frontmatter (see [[SCHEMA#Page Format]])
# Add entry to wiki/index.md
echo "## [$(date +%Y-%m-%d)] ingest | <title>" >> wiki/log.md
```

## Common Pitfalls

1. **Frontend changes not showing** → forgot `npm run build` + hard-refresh
2. **JSON write fails** → used a heredoc instead of Python's `json.dumps` (see AGENTS.md edit protocol)
3. **Tailoring hangs** → invalid API key or network issue; check SSE events in DevTools
4. **Wiki page references stale data** → `data/*.json` changed but a related wiki page (architecture/ADR) wasn't updated to match
5. **CI/CD not triggering** → didn't push to `main`, or the changed files aren't in the `paths` filter (`.github/workflows/build-resume.yml`)

## Related Pages

- [[SCHEMA]] — wiki conventions and operations
- [[system]] — full architecture
- [[pipeline]] — AI tailoring detail
- [[overview]] — project synthesis
