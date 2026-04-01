#!/usr/bin/env python3
"""
Resume Customizer — FastAPI backend.

Serves a Jinja2-templated editor UI, accepts JSON payloads to generate PDFs
or persist data back to disk.

Usage:
    python customizer/server.py
"""

import json
import subprocess
import sys
import tempfile
import shutil
import re
from pathlib import Path

# Ensure customizer/ is on sys.path so `from pipeline import ...` works
# regardless of how the server is started (direct script or uvicorn import).
_CUSTOMIZER_DIR = Path(__file__).resolve().parent
if str(_CUSTOMIZER_DIR) not in sys.path:
    sys.path.insert(0, str(_CUSTOMIZER_DIR))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CUSTOMIZER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CUSTOMIZER_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
RENDER_SCRIPT = PROJECT_ROOT / "scripts" / "render_resume.py"

SECTION_FILES = {
    "profile": "profile.json",
    "contact": "contact.json",
    "education": "education.json",
    "experience": "experience.json",
    "projects": "projects.json",
    "skills": "skills.json",
}

# ---------------------------------------------------------------------------
# pdflatex check
# ---------------------------------------------------------------------------
HAS_PDFLATEX = shutil.which("pdflatex") is not None

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Resume Customizer")
app.mount("/static", StaticFiles(directory=CUSTOMIZER_DIR / "static"), name="static")
templates = Jinja2Templates(directory=CUSTOMIZER_DIR / "templates")


def _load_json(path: Path) -> dict:
    """Load a JSON file, return empty dict if missing."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_all_data() -> dict:
    """Load every section from data/ into a single dict."""
    data = {}
    for section, filename in SECTION_FILES.items():
        data[section] = _load_json(DATA_DIR / filename)
    return data


def _safe_filename(name: str) -> str:
    """Turn a display name into a filename-safe string."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the customizer page with forms pre-populated from JSON."""
    data = _load_all_data()
    return templates.TemplateResponse(
        request,
        "index.html",
        context={"data": data, "data_json": json.dumps(data)},
    )


@app.post("/api/generate")
async def generate(request: Request):
    """
    Accept full JSON payload, generate PDF, stream it back.
    Does NOT overwrite the on-disk JSON files — uses a temp data dir.
    """
    if not HAS_PDFLATEX:
        return JSONResponse(
            status_code=500,
            content={
                "error": "pdflatex not found",
                "details": "Install TeX Live: sudo apt install texlive-latex-base texlive-fonts-extra texlive-latex-extra",
            },
        )

    payload = await request.json()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Write payload sections to temp JSON files
        for section, filename in SECTION_FILES.items():
            section_data = payload.get(section, {})
            (tmp / filename).write_text(
                json.dumps(section_data, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )

        # render_resume.py always writes resume.tex to PROJECT_ROOT
        # (it extracts just the filename from --output). We render
        # a uniquely‑named .tex to avoid clobbering.
        tex_name = "_customizer_tmp.tex"
        result = subprocess.run(
            [
                "python3",
                str(RENDER_SCRIPT),
                "--data-dir",
                str(tmp),
                "--output",
                tex_name,
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        tex_file = PROJECT_ROOT / tex_name
        if result.returncode != 0 or not tex_file.exists():
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Template rendering failed",
                    "details": result.stderr or result.stdout,
                },
            )

        # Run pdflatex from PROJECT_ROOT (so \input{glyphtounicode} resolves)
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_name],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        pdf_file = PROJECT_ROOT / tex_name.replace(".tex", ".pdf")
        if not pdf_file.exists():
            # Clean up .tex
            tex_file.unlink(missing_ok=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "PDF compilation failed",
                    "details": result.stdout[-2000:],
                },
            )

        # Determine download filename
        profile = payload.get("profile", {})
        name = profile.get("name", "resume")
        safe_name = _safe_filename(name)
        download_name = f"resume_{safe_name}.pdf"

        # Move PDF to final name, clean up temp files
        stable_pdf = PROJECT_ROOT / download_name
        shutil.move(str(pdf_file), str(stable_pdf))
        for ext in (".tex", ".aux", ".log", ".out"):
            (PROJECT_ROOT / tex_name.replace(".tex", ext)).unlink(missing_ok=True)

    return FileResponse(
        path=str(stable_pdf),
        filename=download_name,
        media_type="application/pdf",
    )


@app.post("/api/save")
async def save(request: Request):
    """Overwrite the on-disk JSON files with the provided payload."""
    payload = await request.json()

    for section, filename in SECTION_FILES.items():
        section_data = payload.get(section, {})
        (DATA_DIR / filename).write_text(
            json.dumps(section_data, indent=4, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return {"status": "ok", "message": "All data saved to disk."}


@app.post("/api/tailor")
async def tailor(request: Request):
    """
    Multi-stage tailoring pipeline — streams SSE events as each stage completes.
    Accepts JD text, provider config, and current resume data.
    """
    import os

    from pipeline import get_instructor_client, run_pipeline, sse_event

    payload = await request.json()
    jd = payload.get("jd", "")
    config = payload.get("config", {})
    data = payload.get("data", {})

    if not jd.strip():
        return JSONResponse(
            status_code=400, content={"error": "Job description is required."}
        )

    provider = config.get("provider", "openai")
    model = config.get("model", "gpt-4o-mini")
    api_key = config.get("api_key", "").strip()

    if not api_key:
        env_key = f"{provider.upper()}_API_KEY"
        api_key = os.getenv(env_key) or os.getenv("OPENAI_API_KEY")

    if not api_key:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"API Key is required. Please provide it in the UI or set {env_key} / OPENAI_API_KEY environment variable."
            },
        )

    try:
        client = get_instructor_client({**config, "api_key": api_key})
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"error": f"Failed to create API client: {str(e)}"}
        )

    return StreamingResponse(
        run_pipeline(client, model, jd, data),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not HAS_PDFLATEX:
        print("\033[33m[WARNING] pdflatex not found. PDF generation will fail.\033[0m")
        print(
            "  Install: sudo apt install texlive-latex-base texlive-fonts-extra texlive-latex-extra"
        )
    uvicorn.run(app, host="127.0.0.1", port=8000)
