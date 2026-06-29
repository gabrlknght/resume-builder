#!/usr/bin/env python3
"""Lint check wiki health.

Checks performed:
1. **Stale pages** — `last_updated` frontmatter > 30 days old
2. **Orphan pages** — wiki pages not listed in index.md
3. **Missing directories** — expected wiki/ subdirectories

Exit code 0 = all clean. Exit code 1 = issues found (report printed to stderr).
"""

import json
import os
import re
import sys
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_DIR = os.path.join(BASE_DIR, "wiki")
DATA_DIR = os.path.join(BASE_DIR, "data")
STALE_DAYS = 30
TODAY = date.today()

errors = []
warnings = []


def err(msg):
    errors.append(msg)
    print(f"  ✗ {msg}", file=sys.stderr)


def warn(msg):
    warnings.append(msg)
    print(f"  ⚠ {msg}", file=sys.stderr)


def ok(msg):
    print(f"  ✓ {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 1. Stale pages
# ---------------------------------------------------------------------------

def check_stale():
    ok("Checking stale pages...")
    md_files = []
    for root, _, files in os.walk(WIKI_DIR):
        for f in files:
            if f.endswith(".md"):
                md_files.append(os.path.join(root, f))

    stale_count = 0
    # Skip files that intentionally lack last_updated
    skip_stale = {"log.md", "SCHEMA.md"}
    for path in md_files:
        rel = os.path.relpath(path, WIKI_DIR)
        if rel in skip_stale:
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        match = re.search(r"last_updated:\s*(\d{4}-\d{2}-\d{2})", content)
        if not match:
            err(f"Stale: {rel} — no last_updated frontmatter")
            stale_count += 1
            continue

        last = date.fromisoformat(match.group(1))
        days_ago = (TODAY - last).days
        if days_ago > STALE_DAYS:
            rel = os.path.relpath(path, WIKI_DIR)
            err(f"Stale: {rel} — last_updated {last} ({days_ago} days ago, threshold: {STALE_DAYS})")
            stale_count += 1

    if stale_count == 0:
        ok(f"All {len(md_files)} pages up to date")
    return stale_count


# ---------------------------------------------------------------------------
# 2. Orphan pages
# ---------------------------------------------------------------------------

def check_orphans():
    ok("Checking orphan pages...")
    index_path = os.path.join(WIKI_DIR, "index.md")

    if not os.path.exists(index_path):
        err("index.md missing — cannot check orphans")
        return 0

    with open(index_path, "r", encoding="utf-8") as f:
        index_content = f.read()

    # Extract all wiki pages listed in index.md
    listed = set()
    for match in re.finditer(r"\]\(([a-z0-9_/\.]+\.md)\)", index_content, re.IGNORECASE):
        listed.add(match.group(1))

    # index.md and SCHEMA.md are meta-files that don't need to self-reference
    listed.add("index.md")
    listed.add("SCHEMA.md")

    # Find all actual .md files in wiki/
    actual = set()
    for root, _, files in os.walk(WIKI_DIR):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(root, f), WIKI_DIR)
                actual.add(rel)

    orphans = actual - listed
    orphan_count = 0
    for orphan in sorted(orphans):
        err(f"Orphan: {orphan} — not listed in index.md")
        orphan_count += 1

    if orphan_count == 0:
        ok(f"All {len(actual)} pages listed in index.md")
    return orphan_count


# ---------------------------------------------------------------------------
# 3. Missing directories
# ---------------------------------------------------------------------------

def check_directories():
    ok("Checking expected directories...")
    expected_dirs = [
        "applications",
        "decisions",
    ]
    missing = 0
    for d in expected_dirs:
        path = os.path.join(WIKI_DIR, d)
        if not os.path.isdir(path):
            err(f"Missing directory: wiki/{d}/")
            missing += 1

    if missing == 0:
        ok("All expected directories exist")
    return missing


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60, file=sys.stderr)
    print("Wiki Lint — checking wiki/ health", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    stale = check_stale()
    orphans = check_orphans()
    dirs = check_directories()

    total = stale + orphans + dirs
    print("=" * 60, file=sys.stderr)
    if total > 0:
        print(f"\nFAILED: {total} issue(s) found ({stale} stale, {orphans} orphans, {dirs} missing dirs)", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nPASSED: Wiki is healthy ({len(warnings)} warnings)", file=sys.stderr)
        if warnings:
            for w in warnings:
                print(f"  ⚠ {w}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
