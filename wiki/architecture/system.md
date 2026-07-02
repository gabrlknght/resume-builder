---
title: System Architecture
type: architecture
last_updated: 2026-06-16
sources: [AGENTS.md, customizer/server.py, .github/workflows/build-resume.yml]
---

# System Architecture

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| Templating | Jinja2 (HTML) + Jinja2 (LaTeX) |
| Frontend | Vanilla JavaScript (ES6+), no framework |
| PDF Preview | Mozilla pdf.js (embedded in browser) |
| PDF Generation | pdflatex (LaTeX compile) |
| AI Tailoring | instructor + async LLM calls |
| Progress Streaming | Server-Sent Events (SSE) |
| Data Store | Flat JSON files (`data/*.json`) |
| CI/CD | GitHub Actions |

## File Map

```
resume-builder/
├── data/                        # Source-of-truth JSON files
│   ├── profile.json
│   ├── experience.json
│   ├── education.json
│   ├── projects.json
│   ├── skills.json
│   └── contact.json
├── templates/
│   └── resume.tex.j2            # Jinja2 LaTeX template
├── scripts/
│   └── render_resume.py         # JSON → LaTeX renderer
├── customizer/                  # Local web UI
│   ├── server.py                # FastAPI app entry point
│   ├── server_additions.py      # Additional routes
│   ├── pipeline.py              # 4-stage AI tailoring pipeline
│   ├── config.py                # Settings / env config
│   ├── data_utils.py            # JSON read/write helpers
│   ├── history_manager.py       # Tailoring history tracking
│   ├── pdf_generator.py         # pdflatex invocation wrapper
│   ├── static/
│   │   ├── app.js               # Main frontend (source)
│   │   ├── app.min.js           # Minified (served by default)
│   │   ├── style.css            # Styles (source)
│   │   ├── style.min.css        # Minified (served by default)
│   │   ├── api-utils.js         # API call helpers
│   │   ├── dom-utils.js         # DOM manipulation helpers
│   │   ├── form-utils.js        # Form handling helpers
│   │   └── state.js             # Frontend state management
│   └── templates/
│       └── index.html           # Jinja2 HTML template for web UI
└── .github/workflows/
    └── build-resume.yml         # CI/CD: JSON → PDF on push
```

## CI/CD Workflow

GitHub Actions triggers on changes to `data/*.json`, `templates/`, or `scripts/`:

1. Install Python + Jinja2
2. Run `scripts/render_resume.py` → generates `resume.tex`
3. Compile LaTeX via `xu-cheng/latex-action`
4. Create or update a "latest" GitHub Release with the PDF

## Local Web UI

Start with: `python customizer/server.py`

Key UI features:
- Edit all JSON sections visually (forms auto-populated from JSON)
- "Save to Backend" writes edits to `data/*.json`
- Real-time PDF preview (pdf.js)
- AI Tailoring: paste JD → 4-stage pipeline runs → visual diff shown
- BYOK: choose provider + model + API key in UI

## History Tables

Both the **Resume History** and **Cover Letter History** tables have icon-based metrics display:

- **Metrics column** uses emoji icons instead of text labels:
  - 🔢 = tokens (count)
  - ⏱ = elapsed time (e.g. `12.3s`)
  - ⚡ = throughput (e.g. `1002 tok/s`)
- Each icon has a `title` attribute showing the label on hover
- Metrics display across two lines via `white-space: pre-line` (wraps instead of overflowing)
- Table max-width is `1200px` (wide enough to avoid horizontal scroll on typical screens)
- Cell padding is `0.4rem 0.5rem` (top/bottom 0.4rem, left/right 0.5rem) — horizontal padding matches

## Frontend Build

The server serves **minified** files (`app.min.js`, `style.min.css`). After editing `app.js` or `style.css`, run:

```bash
npm run build
```

Then hard-refresh in browser (Ctrl+Shift+R) to see changes.

## Edit Protocol

From `AGENTS.md`:
- Read file before editing
- One logical change per tool call
- Re-read after edit to verify
- Never fix a broken edit with another edit — report and stop
- JSON files: always write via Python (`json.dumps`), never heredocs

## Related Pages

- [[pipeline]] — AI tailoring detail
- [[overview]] — project synthesis
