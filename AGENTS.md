# AI Agent Integration Details

This project leverages both automated CI/CD and AI-assisted workflows to build, maintain, and customize professional resumes from structured JSON data.

## Two Workflows

- **CI/CD (Zero Setup)**: Push JSON changes to GitHub → PDF auto-generated via GitHub Actions. No local installation required.
- **Local Web UI (Power User)**: Run `customizer/server.py` → Edit JSON visually, preview PDF in real-time, generate on-demand with full local control.

## Core Architecture

- **JSON Data Structure**: The `data/*.json` schema (profile, experience, education, projects, skills, contact) cleanly separates content from presentation.
- **LaTeX Templates**: `templates/resume.tex.j2` uses Jinja2 templating to inject JSON data into a professional LaTeX document.
- **Build Scripts**: `scripts/render_resume.py` parses templates, loads data, and generates `.tex` output.

## Local Web UI (customizer/)

The built-in web interface for power users who want local control:

- **Stack**: FastAPI + Uvicorn (backend), Jinja2 (templating), Vanilla JavaScript (frontend).
- **Design System**: Minimalist black-and-white with JetBrains Mono font (brutalist, developer-centric).
- **PDF Preview**: Real-time preview via Mozilla's `pdf.js` embedded in browser.
- **Data Persistence**: Reads from/writes to `data/*.json` files via "Save to Backend" button.

## The `tailor-resume` AI Skill

This repository is designed to be highly interoperable with AI coding assistants. Use the **`resume-builder-tailor`** AI skill to adapt your resume for specific job descriptions.

- **Skill Location**: https://github.com/jangwanAnkit/skills/tree/main/resume-builder-tailor
- **How it works**: An AI agent equipped with this skill reads `data/*.json` files, analyzes a job description, and rewrites bullet points, skills, and summary to match the target role.
- **Usage**: Ask your AI assistant to "tailor resume to [Job Description]" — it will safely update the JSON structure.

### Built-in Web Integration (Phase 1)
The core logic of the `resume-builder-tailor` skill is now natively integrated into the `customizer/` Local Web UI backend(v1 has it in a single prompt, this will be improved).
- **BYOK Support**: Users can specify their provider (OpenAI, Gemini, Cerebras, OpenRouter), API Key, and Model directly via the local web UI (`/api/tailor`).
- **Dynamic Diffing**: The UI automatically parses the LLM agent's output and renders a diff in the Preview pane, making hallucination auditing effortless.
- **JD Match Scoring**: The agent computes an out-of-10 relevance score and structural gap analysis against the target Job Description to highlight exactly where the resume falls short.

## CI/CD Workflow

GitHub Actions (`.github/workflows/build-resume.yml`) auto-generates PDFs on every push to `main`:

1. Triggers on changes to `data/*.json`, `templates/`, or `scripts/`
2. Installs Python + Jinja2
3. Runs `scripts/render_resume.py` to generate LaTeX
4. Compiles LaTeX to PDF via `xu-cheng/latex-action`
5. Creates/updates a "latest" release with the PDF
