# Wiki Schema — Resume Builder

This is the operating manual for the LLM-maintained wiki of the `resume-builder` project. Claude reads this file at the start of every wiki-related task to understand the structure, conventions, and workflows.

## Purpose

This wiki is the persistent knowledge layer sitting between the raw project files and you. It compiles, cross-references, and synthesizes knowledge so it doesn't have to be re-derived from JSON and source files every session. The wiki grows richer with every job application, every architectural decision, and every tailoring session.

**The JSON files in `data/` are the source of truth for resume content. When they change, update the matching wiki pages.**

---

## Directory Structure

```
wiki/
├── SCHEMA.md                  # This file — the operating manual
├── index.md                   # Catalog of all pages (always read first when querying)
├── log.md                     # Append-only chronological log of all wiki activity
├── overview.md                # High-level project synthesis
├── architecture/
│   ├── system.md              # Core system architecture (FastAPI, JSON→LaTeX, CI/CD)
│   └── pipeline.md            # AI tailoring 4-stage pipeline detail
├── resume/
│   ├── profile.md             # Avik's current profile, title, bio, contact
│   ├── experience.md          # Full work history with company/role/dates/bullets
│   ├── projects.md            # All projects with tech stacks and status
│   ├── skills.md              # Skills by category
│   └── education.md           # Education + contact info
└── applications/
    └── YYYY-MM-DD_company_role.md   # One file per job application
```

---

## Page Format

Every wiki page uses this frontmatter:

```yaml
---
title: Page Title
type: overview | architecture | resume | application | synthesis
last_updated: YYYY-MM-DD
sources: [file or URL that backs this page]
---
```

Body uses standard markdown. Link to related pages with `[[page-name]]` (Obsidian-style wikilinks).

---

## Operations

### Ingest

When the user provides a new source (job description, article, decision):

1. Read the source.
2. Discuss key takeaways with the user.
3. Write or update the relevant wiki page(s).
4. If it's a job application, create `applications/YYYY-MM-DD_company_role.md`.
5. Update `index.md` with the new page.
6. Append an entry to `log.md`.

### Query

When the user asks a question about the project or resume:

1. Read `index.md` to find relevant pages.
2. Read those pages.
3. Synthesize and answer with wiki citations.
4. If the answer is valuable and non-obvious, offer to file it as a new wiki page.

### Update (Resume Sync)

When `data/*.json` files are edited:

1. Update the matching `resume/*.md` wiki page to reflect the change.
2. Update `last_updated` frontmatter.
3. Append an entry to `log.md`.

### Lint

Periodically (user-requested):

1. Check for pages with stale `last_updated` dates.
2. Check for orphan pages (no inlinks from index or other pages).
3. Check for contradictions between resume wiki pages and `data/*.json`.
4. Suggest new application pages for tailoring sessions not yet filed.
5. Identify concepts worth their own page that are only mentioned inline.

---

## Application Page Format

Each job application gets its own page. Template:

```markdown
---
title: Company — Role
type: application
date: YYYY-MM-DD
status: tailored | submitted | interviewed | offer | rejected | skipped
jd_url: URL or "N/A"
jd_relevance: X/10
last_updated: YYYY-MM-DD
sources: [jd url or paste]
---

# Company — Role

## JD Summary
[2-3 sentence summary of the role and key requirements]

## Relevance Rating: X/10
- **Matching skills:** [list]
- **Gaps:** [list]
- **Recommendation:** Proceed / Skip / Partial

## Changes Made
[Bullet list of what was changed in which JSON file]

## Notes
[Anything notable — recruiter feedback, interview prep, outcome]
```

---

## Log Format

Every entry in `log.md` starts with:

```
## [YYYY-MM-DD] <type> | <short title>
```

Types: `ingest`, `query`, `update`, `lint`, `application`, `decision`

This makes the log grep-able: `grep "^## \[" wiki/log.md | tail -10`

---

## Key Rules

- **Never edit `data/*.json` from within wiki operations.** Wiki pages describe what's in the JSON; only tailoring sessions modify the JSON.
- **The index is always up to date.** Every new page gets an entry in `index.md` immediately.
- **Application pages are never deleted**, even after rejection — they record what was tried.
- **Resume wiki pages mirror the JSON.** If they diverge, the JSON wins.
- **Cross-link generously.** An application page should link to `[[experience]]`, `[[skills]]`, etc.
