# AI Agent Integration Details

This project leverages both automated CI/CD and AI-assisted workflows to build, maintain, and customize professional resumes from structured JSON data. Large parts of this repository were designed and implemented by an AI agent acting as a pair-programmer.

## Core Architecture Built by AI
The foundational architecture of this resume builder was established by an AI agent:
- **JSON Data Structure**: The `data/*.json` schema (profile, experience, education, projects, skills) was modeled by an AI to cleanly separate content from presentation.
- **LaTeX Templates**: The `templates/resume.tex.j2` file uses Jinja2 templating syntax to inject JSON data into a professional LaTeX document, automatically escaping special characters.
- **Build Scripts**: The python rendering engine (`scripts/render_resume.py`) was written to parse the templates, load local data, and generate the final `.tex` output.

## UI Customizer Built by AI
The local web UI (`customizer/`) was designed and implemented by an AI agent using the `minimalist-bw-ui` design system.
- **Stack**: FastAPI (backend), Jinja2 (templating), Vanilla JavaScript (frontend behavior).
- **Design System**: Strictly enforced minimalist styling — black backgrounds (`#000`), white text (`#fff`), and the `JetBrains Mono` typeface. This provides a focused, brutalist, and developer-centric aesthetic.
- **Preview Integration**: The real-time PDF preview is embedded directly in the browser via Mozilla's `pdf.js`, closely mirroring an Overleaf-style editing experience without requiring external tooling (other than a local `pdflatex` installation).
- **Data Persistence**: The UI reads directly from the `data/*.json` files and can persist changes back to them via the "Save to Backend" functionality.

## The `tailor-resume` AI Skill
This repository is designed to be highly interoperable with AI coding assistants. You can use the local **`tailor-resume` AI skill** to quickly update and adapt your resume for specific job descriptions. 
- **How it works**: An AI agent equipped with the `tailor-resume` skill can read the existing `data/*.json` files, analyze a provided job description, and automatically rewrite your experience bullet points, skills, and summary to better match the target role.
- **Usage**: Simply ask your AI assistant (e.g., "Use the tailor-resume skill to update my resume for [Job Description]") and it will safely parse and update the JSON structure for you. 

## Continuous Integration Workflow
While the UI enables easy local editing, the core generation pipeline remains automated via GitHub Actions (`.github/workflows/resume-builder.yml`).
Updates pushed to the repository are automatically processed by a CI agent running Ubuntu, which sets up `texlive`, renders the Jinja2 templates via `scripts/render_resume.py`, compiles the LaTeX source to a PDF, and creates a repository release.
