---
title: Wiki Index
type: index
last_updated: 2026-07-06
sources: [wiki/SCHEMA.md, data/profile.json, data/experience.json, data/projects.json, data/skills.json, data/education.json]
---

# Wiki Index — Resume Builder

Read this file first when answering queries. Each entry links to a wiki page with a one-line summary.

## Meta

- [SCHEMA](SCHEMA.md) — Operating manual: directory layout, page formats, operations, rules
- [Log](log.md) — Chronological record of all wiki activity (ingest, update, lint, applications)
- [Overview](overview.md) — High-level synthesis: what this project is and how it all fits together
- [CLAUDE.md](../CLAUDE.md) — Claude Code guidance: commands, architecture summary, wiki/edit/JSON rules
- [DEVELOPMENT](DEVELOPMENT.md) — Setup instructions, common pitfalls, local UI troubleshooting

## Architecture

- [System Architecture](architecture/system.md) — FastAPI backend, JSON→LaTeX pipeline, CI/CD, web UI stack
- [AI Tailoring Pipeline](architecture/pipeline.md) — 5-stage LLM pipeline (added Stage 3.5: keyword mapping): JD analysis, matching, tailoring, keyword traceability, validation

## Decisions

- [Decisions](decisions/index.md) — Recorded architectural and project decisions with rationale (ADR-001 through ADR-008)

## Applications

> One page per tailoring session. Templates in [[SCHEMA#Application Page Format]].

- [applications/](applications/) — Directory for application pages (empty — add `YYYY-MM-DD_company_role.md` per session)
