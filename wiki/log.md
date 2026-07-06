# Wiki Log

Append-only. Each entry: `## [YYYY-MM-DD] <type> | <title>`

Grep for recent activity: `grep "^## \[" wiki/log.md | tail -10`

---

## [2026-06-25] ingest | CLAUDE.md created

Created `CLAUDE.md` at the repo root for Claude Code guidance. Sources ingested: `README.md`, `AGENTS.md`, `customizer/TAILOR_SKILL.md`, `wiki/` (all pages), `ruff.toml`, `package.json`. Content covers: dev commands, frontend build step (minified files served), system architecture, 4-stage AI pipeline, wiki conventions (from llm-wiki.md gist), edit protocol, JSON write rules, hard-stop rules, and tailoring immutability table. Also bootstrapped persistent memory files in `~/.claude/projects/.../memory/`.

---

## [2026-06-16] ingest | Initial wiki bootstrap

Wiki created from scratch. Seeded from: `AGENTS.md`, `customizer/TAILOR_SKILL.md`, `data/*.json`. Pages created: SCHEMA, index, log, overview, architecture/system, architecture/pipeline, resume/profile, resume/experience, resume/projects, resume/skills, resume/education.

## [2026-06-28] update | Wiki restructuring and health tooling

Added project documentation and wiki health infrastructure. Dropped resume wiki pages — example data has no value in wiki.

- Created wiki/decisions/index.md with 5 ADRs (flat JSON, Jinja2, 4-stage pipeline, BYOK, minified assets)
- Created wiki/DEVELOPMENT.md with setup, troubleshooting, and wiki maintenance guide
- Fixed index.md: updated last_updated, added new pages
- Added YAML frontmatter to SCHEMA.md
- Created wiki/applications/ directory
- Created scripts/wiki_lint.py: checks stale pages (>30d), orphan pages (not in index), missing directories
- Updated .github/workflows/build-resume.yml: added wiki lint step before LaTeX compilation

## [2026-06-28] update | Fixed stale references from wiki restructuring

Self-review caught doc/code drift introduced by the previous entry. Fixes:

- SCHEMA.md: directory diagram and "Update" operation still described removed `wiki/resume/*.md` mirror pages — replaced with `decisions/` and a "Decision or Architecture Change" operation
- SCHEMA.md + CLAUDE.md: "Key Rules" / "Wiki sync rule" still said wiki mirrors `data/*.json` — corrected to state JSON is sole source of truth, not mirrored
- Created root `Makefile` with `wiki-lint`, `wiki-sync` (no-op reminder), and `pdf` targets — `DEVELOPMENT.md` referenced `make wiki-sync`/`make wiki-lint`/`make pdf` with no Makefile to back them
- scripts/wiki_lint.py: docstring claimed a "JSON-vs-wiki mismatch" check that was never implemented — removed from docstring
- build-resume.yml: added `continue-on-error: true` to the wiki lint step so wiki staleness/orphans never block resume PDF releases

## [2026-06-29] update | llama.cpp provider + reasoning disable + output token cap

User moved to AMD machine, added llama.cpp as a local LLM provider alongside ollama.

- Created `wiki/decisions/2026-06-29_llamacpp-provider.md` — ADR-006 documenting the decision
- Code changes: `customizer/pipeline.py` (llamacpp provider config, `MAX_OUTPUT_TOKENS=2048`, `_local_extra_kwargs` to disable thinking), `customizer/server.py` (base_url normalization for llamacpp), `customizer/static/app.js` (model fetch from `/v1/models`, default settings), `customizer/templates/index.html` (dropdown + datalist entries)
- Key features: reasoning chains disabled for structured output, 2048-token hard ceiling on all pipeline calls, auto model discovery from running llama.cpp server

## [2026-07-02] update | Semantic ATS Mapping — post-review bug fixes and improvements

Senior code review of the `semantic-ats-mapping` branch. Two P0 bugs, two P1 design gaps, and three P2/P3 improvements identified and fixed. Overall assessment: local model delivered a solid B+ — correct on happy path, architecture sound, bugs confined to last-mile wiring and edge-case logic.

### Follow-up: Stage 3.5 SSE stage ID

- Review comment noted that emitting `stage: 3.5` caused the frontend progress handler (which mapped only integer stages 1–4) to ignore the new half-step.
- Changed backend SSE `stage` for the Keyword Mapping half-step from `3.5` to integer `35`.
- Updated `customizer/static/app.js` `handlePipelineEvent()` stage map to include `35` and relabel all tailoring stages as 1/5 through 4/5.
- Updated `customizer/pipeline.py` module docstring and `wiki/architecture/pipeline.md` to document the integer stage ID convention.

### Bugs fixed

- **[P0] Cover letter tone silently dropped** — `tone` was received by `run_cover_letter_pipeline()` but never forwarded to `generate_cover_letter()`. Cover letter tone UI selector had no effect. Fixed by adding `tone` param to `generate_cover_letter()`, converting `COVER_LETTER_SYSTEM` to a format string with `{tone}` placeholder, and threading it through the call.
- **[P0] Keyword matrix `break` dropped multi-keyword bullets** — `break` after first keyword match per bullet caused all subsequent keyword matches in the same bullet to be silently skipped. Removed `break`; deduplication set at the end handles uniqueness.
- **[P1] Positional diff invalidated by bullet reordering** — `_diff_bullets()` matched by index, but Stage 3 prompts explicitly allow reordering bullets. If the LLM reordered bullets, diffs produced incorrect "original → tailored" pairs. Removed `_diff_bullets()` entirely; `build_keyword_matrix()` now iterates all tailored bullets directly.

### Design improvements

- **[P1] Section-specific strategy addenda restored** — consolidation into `STAGE3_REWRITE_STRATEGY` removed experience and projects rules ("may reorder bullets", "reorder techs only, no additions"). Added `STAGE3_EXPERIENCE_STRATEGY` and `STAGE3_PROJECTS_STRATEGY` as section-specific addenda (same pattern as `STAGE3_PROFILE_STRATEGY`).
- **[P2] `tone_cues` wired into Stage 3** — Stage 1 paid to extract JD tone cues but Stage 3 discarded them. Now passed to each `tailor_*()` user message as `JD tone cues: ...`.
- **[P2] Redundant tone removed from user messages** — `f"Tone: {tone}\n\n"` was in every user message AND in the system prompt. Removed from user messages.
- **[P3] `_tailor_context()` return annotation corrected** — was `-> str`, now `-> dict`.
- **[P3] `Semantic-ATS-Mapping.md` broken template variable** — `{{resume_\ntext}}` split across lines fixed to `{{resume_text}}`.

### Files changed
- `customizer/pipeline.py` — all of the above
- `Semantic-ATS-Mapping.md` — template variable fix
- `wiki/decisions/2026-07-02_semantic-ats-mapping.md` — Amendments section added
- `wiki/decisions/index.md` — ADR-007 status updated to "Accepted, Amended"
- `wiki/architecture/pipeline.md` — corrected implementation descriptions

---

## [2026-07-02] update | Semantic ATS Mapping framework

Implemented Semantic ATS Mapping — a framework for producing more natural, contextually-aware resume rewrites via semantic concept extraction, unified rewriting strategy, keyword traceability, and tone control.

### Decision
- Created `wiki/decisions/2026-07-02_semantic-ats-mapping.md` — ADR-007 documenting the framework

### Pipeline changes (`customizer/pipeline.py`)
- `JDAnalysis` model extended with `semantic_concepts: list[str]` and `tone_cues: str`
- `STAGE1_SYSTEM` prompt upgraded to "world-class Executive Resume Writer and ATS Algorithm Expert" with semantic mapping instructions
- Replaced 3 disjointed Stage 3 prompts with unified `STAGE3_REWRITE_STRATEGY` + `STAGE3_PROFILE_STRATEGY`
- Added `_tailor_context()` helper for building shared context dict (tone, must_haves, semantic concepts, keywords)
- Added `build_keyword_matrix()` — deterministic diff-based keyword traceability (Stage 3.5)
- Added `keyword_mapping` to final output via `validate_and_assemble()`
- Added `tone` parameter to `run_pipeline()`, `run_cover_letter_pipeline()`, and all `tailor_*()` functions
- Updated `validate_and_assemble()` to inject `keyword_matrix` into final output

### API changes (`customizer/server.py`)
- `/api/tailor` and `/api/cover-letter` extract `tone` from payload/config (default `"professional"`)
- Pass `tone` through to pipeline functions

### Frontend changes
- `customizer/templates/index.html` — added tone dropdown (Professional, Formal, Innovative, Collaborative, Technical, Conversational) in both tailoring and cover letter sections
- `customizer/static/app.js` — `tailorResume()` and `generateCoverLetter()` read `#ai-tone` / `#cl-tone` and include in API payloads

### Architecture impact
- Pipeline now has 5 stages (was 4): added Stage 3.5 Keyword Mapping
- `index.md` updated to reflect 5-stage pipeline
- `architecture/pipeline.md` updated with semantic mapping, unified strategy, tone control, and keyword mapping details
- `decisions/index.md` updated with ADR-007 entry

---

## [2026-07-02] update | Generation metrics tracking (tokens/time) + llamacpp timeout fix

Added end-to-end generation metrics (completion tokens + wall-clock elapsed time) across the tailoring and cover-letter pipelines, plus fixed a Stage 3 request-timeout bug on the `llamacpp` provider surfaced while testing this feature.

### Decision
- Created `wiki/decisions/2026-07-02_generation-metrics-tracking.md` — ADR-008 documenting the feature and the related timeout fix

### Pipeline changes (`customizer/pipeline.py`)
- Added `MetricsTracker` class — async-context-manager wrapper around each `instructor` LLM call, summing `completion_tokens` and tracking wall-clock elapsed time since pipeline start
- `analyze_jd`, `tailor_profile`, `tailor_experience`, `tailor_projects`, `tailor_all_sections`, `generate_cover_letter` now accept an optional `tracker` param
- `run_pipeline` and `run_cover_letter_pipeline` attach `{elapsed_seconds, total_tokens}` to the `"final"` SSE event as `data.timing`
- Raised `llamacpp` client `timeout` 120s → 600s (`get_instructor_client`) — Stage 3's 3 concurrent calls queue behind each other on typical single-slot local llama.cpp servers, so the last-queued call could exceed the old timeout while still waiting

### History changes (`customizer/history_manager.py`, `customizer/server.py`)
- `save_resume_history` / `save_cover_letter_history` accept a `timing` field, written to `_meta.json` only when present (omitted, not `null`, for backward compatibility with pre-existing entries)
- `/api/generate` passes `incoming_meta.get("timing")` through from the frontend's `_meta` payload

### Frontend changes (`customizer/static/app.js`)
- New shared `renderTimingHtml()` / `formatDuration()` helpers
- Metrics line added to both the AI-tailoring diff preview (`applyTailoredData`) and the cover-letter preview (`renderCoverLetterPreview`)
- New "METRICS" column in both resume and cover-letter history tables (tok/tok-s/elapsed, computed client-side)
- Stats tab chart: new dashed "Avg tok/s" line plotted against a secondary right-side axis (`y1`), separate from the left count axis; tooltip now also shows avg generation time per bucket

### Stats backend changes (`customizer/server_additions.py`)
- `_aggregate_history` computes `avg_tokens_per_sec` and `avg_elapsed_seconds` per bucket from whatever entries in that bucket carry `timing` data; `None` for buckets with no timed entries

### Architecture impact
- `architecture/pipeline.md` updated: noted `MetricsTracker` cross-cutting instrumentation and the local-provider queuing behavior behind the timeout fix
- `decisions/index.md` updated with ADR-008 entry

## [2026-07-02] update | History table metrics icons + table width expansion

Improved the history tables' metrics display and widened both table containers for better readability.

### Frontend changes (`customizer/static/app.js`)
- Replaced text-based metrics labels (`xxxxx tokens / xxx.xxs (xx tok/s)`) with three emoji icons:
  - 🔢 = tokens, ⏱ = elapsed time, ⚡ = throughput (tok/s)
- Each icon is wrapped in a `<span title="...">` so hovering shows the label ("tokens", "time", "rate")
- Metrics now span two lines via `<br/>` breaks inside each cell, wrapped with `white-space: pre-line`
- This makes rows narrower and eliminates the horizontal scroll bar that was previously needed

### CSS changes (`customizer/static/style.css`)
- Added `.section#section-history, .section#section-clhistory { max-width: 1200px; }` — widens both history tables from the default 600px
- History table cell padding remains `0.4rem 0.5rem` (left/right already matched)
- Other sections (profile, tailoring, cover letter, stats) stay at 600px

### Wiki impact
- `wiki/architecture/system.md` updated: new **History Tables** section documenting icon-based metrics display, hover titles, line wrapping, and table dimensions

---

## [2026-07-06] update | Auto-save settings, debounced auto-save, and save mode selector

Added auto-save with debounced timer and save mode selector to the local web UI.

### Decision
- Replaced the single "SAVE TO BACKEND" button as the only persistence mechanism with an auto-save option
- Auto-save fires 2 seconds after typing stops, giving a frictionless editing experience
- Manual mode retained for users who want explicit control over when changes are persisted

### Frontend changes (`customizer/static/app.js`)
- Added `loadSettings()` — reads `localStorage('resume-save-mode')` (default `'auto'`), sets radio button state
- Added `applySettings()` — writes mode to localStorage, updates save indicator and unsaved changes warning
- Added `updateSaveIndicator()` — shows gear icon (⚙️) for auto mode, floppy disk (💾) for manual mode
- Added `scheduleAutoSave()` — sets `_hasUnsavedChanges = true`, clears timer, schedules 2s `setTimeout` → `saveToBackend(true)`
- Added `clearAutoSaveTimer()` — clears pending auto-save timer
- Added `updateUnsavedChangesWarning()` — toggles pulsing orange "UNFINISHED" warning in manual mode only
- Added `showTopNotification()` — shows fixed top bar with message, auto-hides after 2.5s
- Added `updateLastSavedIndicator()` — shows "SAVED HH:MM:SS" after each successful save
- Modified `saveToBackend(isAutoSave)` — accepts `isAutoSave` param; auto saves show top notification instead of toast, don't show button loading state
- Refactored card input handlers to use delegated listeners on parent containers:
  - Education: delegated listener on `#education-list`
  - Experience: delegated listener on `#experience-list` (handles both field inputs and detail textareas)
  - Projects: delegated listener on `#projects-list`
  - Skills: delegated listener on `#skills-list`
- Removed per-card inline `addEventListener` calls — each card creation function no longer attaches listeners (cleaner, fewer DOM operations)

### CSS changes (`customizer/static/style.css`)
- Added `.header-actions-group` — groups gear icon + save-mode indicator with no gap
- Added `.action-separator` — 14px white horizontal connector between gear icon and save-mode button
- Added `.last-saved-indicator` — 10px muted text, hidden until first save
- Added `.unsaved-changes-warning` — 10px orange text, hidden by default, pulsing animation (`@keyframes pulse-warning`)
- Added `.top-notification` — fixed top bar, slides in from above, auto-hides after class removal
- Added `.settings-modal` — dark overlay (rgba 0,0,0,0.85), centered, z-index 200
- Added `.settings-panel` — dark background, bordered, centered content panel
- Added `.settings-option` — radio button + label layout, hover background, checked state highlight
- Added `.option-label`, `.option-title`, `.option-desc`, `.option-indicator` — settings modal typography
- Added `.settings-footer` — align buttons right

### HTML changes (`customizer/templates/index.html`)
- Added `#last-saved-indicator` span in header
- Added `#unsaved-changes-warning` span in header (pulsing "UNFINISHED" warning)
- Added header actions group with gear icon button (`#btn-settings`) and save-mode indicator button (`#save-mode-indicator`)
- Added settings modal with radio buttons (auto/manual) and apply/cancel buttons
- Added top notification bar div (`#top-notification`)
- Added inline script for modal open/close events (gear icon click, save-mode indicator click, Escape key, click-outside)

### Architecture impact
- `architecture/system.md` updated with new **Auto-Save Architecture** section documenting save modes, key implementation details, and UI components
- `index.md` updated last_updated timestamp

### Files changed
- `customizer/static/app.js` — auto-save logic, delegated listeners, settings modal handlers
- `customizer/static/style.css` — auto-save UI styling (notification bar, modal, save mode indicator, warning)
- `customizer/templates/index.html` — settings modal, header controls, notification bar
