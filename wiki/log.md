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
