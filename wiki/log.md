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
