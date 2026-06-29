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
