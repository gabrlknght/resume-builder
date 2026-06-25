# Wiki Log

Append-only. Each entry: `## [YYYY-MM-DD] <type> | <title>`

Grep for recent activity: `grep "^## \[" wiki/log.md | tail -10`

---

## [2026-06-25] ingest | CLAUDE.md created

Created `CLAUDE.md` at the repo root for Claude Code guidance. Sources ingested: `README.md`, `AGENTS.md`, `customizer/TAILOR_SKILL.md`, `wiki/` (all pages), `ruff.toml`, `package.json`. Content covers: dev commands, frontend build step (minified files served), system architecture, 4-stage AI pipeline, wiki conventions (from llm-wiki.md gist), edit protocol, JSON write rules, hard-stop rules, and tailoring immutability table. Also bootstrapped persistent memory files in `~/.claude/projects/.../memory/`.

---

## [2026-06-16] ingest | Initial wiki bootstrap

Wiki created from scratch. Seeded from: `AGENTS.md`, `customizer/TAILOR_SKILL.md`, `data/*.json`. Pages created: SCHEMA, index, log, overview, architecture/system, architecture/pipeline, resume/profile, resume/experience, resume/projects, resume/skills, resume/education.
