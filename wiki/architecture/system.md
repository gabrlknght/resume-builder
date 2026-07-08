---
title: System Architecture
type: architecture
last_updated: 2026-07-07
sources: [AGENTS.md, customizer/server.py, .github/workflows/build-resume.yml, customizer/static/app.js]
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
│   ├── pipeline.py              # 5-stage AI tailoring pipeline (1–4, plus 3.5)
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
- AI Tailoring: paste JD → 5-stage pipeline runs → visual diff shown
- BYOK: choose provider + model + API key in UI
- **Auto-save**: debounced auto-save (2s after typing stops) when auto mode is active, with top notification bar flashing "AUTO-SAVED"/"AUTO-SAVE FAILED"
- **Save mode selector**: gear icon → settings modal to toggle between auto-save and manual-only modes, persisted in localStorage
- **Unsaved changes warning**: pulsing "UNFINISHED" warning (orange) when unsaved changes exist in manual mode
- **Last saved indicator**: shows "SAVED HH:MM:SS" timestamp after each save, appears only after first save
- **Settings modal**: dark overlay with radio buttons for auto/manual save mode, accessible via gear icon or save-mode indicator button
- **Delegated event listeners**: all card input handlers (education, experience, projects, skills) use delegated listeners on parent containers for cleaner event management
- **Header actions group**: gear icon + save-mode indicator grouped with a white horizontal connector for visual cohesion

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

## Auto-Save Architecture

### Save Modes

- **Auto-save**: 2-second debounce timer fires `saveToBackend(true)` after typing stops. Top notification bar flashes "AUTO-SAVED" on success or "AUTO-SAVE FAILED" on error. Timer is cleared on each new keystroke.
- **Manual**: no debounced timer. User must click "SAVE TO BACKEND". Pulsing orange "UNFINISHED" warning appears when there are unsaved changes.

### Key Implementation Details

- Save mode persisted in `localStorage('resume-save-mode')` (default: `'auto'`)
- `saveToBackend(isAutoSave)` distinguishes auto vs manual saves — auto saves don't show the "SAVING…" button state, don't show the toast, and show the top notification bar instead
- `_hasUnsavedChanges` boolean tracks manual-mode unsaved state
- `scheduleAutoSave()` sets `_hasUnsavedChanges = true`, clears timer, and schedules a 2s `setTimeout` → `saveToBackend(true)`
- `clearAutoSaveTimer()` clears the pending timer
- All card input handlers (education, experience, projects, skills) call `scheduleAutoSave()` via delegated `input` event listeners on parent containers
- Scalar field inputs use the existing per-field `scheduleAutoSave()` call
- Settings modal: gear icon (`#btn-settings`) and save-mode indicator (`#save-mode-indicator`) both open the modal; Escape key closes it; clicking outside the panel also closes it
- `updateSaveIndicator()` shows a gear icon (⚙️) for auto mode or a floppy disk (💾) for manual mode next to the save-mode button
- `updateLastSavedIndicator()` shows the timestamp after each successful save
- `updateUnsavedChangesWarning()` toggles the pulsing orange warning in manual mode only

### UI Components

- Top notification bar (`#top-notification`) — fixed, slides in from top, auto-hides after 2.5s
- Settings modal (`#settings-modal`) — dark overlay, centered panel with radio buttons and apply/cancel buttons
- Last saved indicator (`#last-saved-indicator`) — 10px muted text, hidden until first save
- Unsaved changes warning (`#unsaved-changes-warning`) — 10px orange text with pulse animation, hidden in auto mode
- Header actions group — gear icon + save-mode indicator grouped with a white horizontal connector (`#action-separator`)

## Theme & Font Customization

Users can customize the UI appearance via a theme modal (`#theme-modal`), accessible via the "THEME" button in the header.

### Color Schemes (5)

| Theme   | Background | Accent    | Vibe              |
|---|---|---|---|
| Default | `#000` / `#fff` | `#000` | Classic black & white |
| Darkslime | `#0a0a0a` | `#00ff41` | Terminal green on dark |
| Crimson | `#1a0000` | `#dc2626` | Deep red accent |
| Ocean   | `#001a2e` | `#0ea5e9` | Ocean blue accent |
| Sunset  | `#1a1000` | `#f97316` | Warm orange/peach |

### Fonts (4)

| Font Family | Style |
|---|---|
| JetBrains Mono | Monospace — default |
| IBM Plex Mono | Monospace — clean, readable |
| Inter | Sans-serif — modern, geometric |
| Space Mono | Monospace — retro, wide |

### Implementation

- Theme/font selections persisted in `localStorage('resume-theme')` and `localStorage('resume-font')`
- Applied via CSS custom properties (`--bg`, `--text`, `--accent`, `--secondary`, `--border`, `--font-main`, `--font-mono`)
- Font changes load Google Fonts dynamically via `document.createElement('link')`
- The `#000000` theme-color meta tag was removed and replaced with dynamic CSS — browser UI elements no longer match the page theme
- ADR-009 documents this decision

## Related Pages

- [[pipeline]] — AI tailoring detail
- [[overview]] — project synthesis
