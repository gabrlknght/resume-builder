---
title: Theme Fonts + Color Settings
date: 2026-07-07
status: Accepted
---

# ADR-009: Theme Fonts + Color Settings

- **Date:** 2026-07-07
- **Status:** Accepted
- **Context:** The web UI had a single color scheme (black and white) and a single font (JetBrains Mono). Users wanted personalization — the ability to customize the look and feel without forking the codebase.

- **Decision:** Added a theme modal with 5 color schemes (Default, Darkslime, Crimson, Ocean, Sunset) and 4 Google Fonts (JetBrains Mono, IBM Plex Mono, Inter, Space Mono). Theme and font selections are persisted in `localStorage` and applied via CSS custom properties and dynamic font loading.

- **Consequences:**
  - + Users can personalize the UI without forking
  - + Theme/font choices persist across sessions via `localStorage`
  - + CSS custom properties (`--bg`, `--text`, `--accent`, `--secondary`, `--border`, `--font-main`, `--font-mono`) make theming trivial to extend
  - - Google Fonts loading adds external HTTP requests (4 font families × 2 weights each = 8 font files)
  - - The `#000000` theme-color meta tag was removed and replaced with dynamic CSS — browser UI elements (tab bar, status bar) no longer match the page theme
