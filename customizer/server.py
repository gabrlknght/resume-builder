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
from datetime import datetime as dt_obj
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

HISTORY_DIR = DATA_DIR / "history"
CL_HISTORY_DIR = DATA_DIR / "cl-history"

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


def _get_history_dir(dt, safe_name: str) -> Path:
    """Return (and create) the timestamped folder for a history entry."""
    ts = dt.strftime("%Y%m%d_%H%M%S")
    folder = HISTORY_DIR / dt.strftime("%Y") / dt.strftime("%m") / f"{ts}_{safe_name}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _scan_history_entries() -> list:
    """Walk HISTORY_DIR for _meta.json files and return list sorted newest-first."""
    entries = []
    if not HISTORY_DIR.exists():
        return entries
    for meta_file in HISTORY_DIR.rglob("_meta.json"):
        try:
            entries.append(json.loads(meta_file.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries


def _scan_cl_history_entries() -> list:
    """Walk CL_HISTORY_DIR for _meta.json files and return list sorted newest-first."""
    entries = []
    if not CL_HISTORY_DIR.exists():
        return entries
    for meta_file in CL_HISTORY_DIR.rglob("_meta.json"):
        try:
            entries.append(json.loads(meta_file.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries


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
    incoming_meta = payload.pop("_meta", {}) or {}

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
                sys.executable,
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

        # Determine download filename + history folder
        profile = payload.get("profile", {})
        name = profile.get("name", "resume")
        safe_name = _safe_filename(name)
        now = dt_obj.now()
        ts_str = now.strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"{safe_name}_{ts_str}.pdf"

        # Save to history folder
        hist_dir = _get_history_dir(now, safe_name)
        stable_pdf = hist_dir / pdf_filename
        shutil.move(str(pdf_file), str(stable_pdf))

        # Write resume data snapshot
        (hist_dir / "resume_data.json").write_text(
            json.dumps(payload, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

        # Build relative entry id (YYYY/MM/folder_name)
        entry_id = str(stable_pdf.parent.relative_to(HISTORY_DIR))

        # Write metadata sidecar
        meta = {
            "id": entry_id,
            "timestamp": now.isoformat(timespec="seconds"),
            "profile_name": name,
            "company": incoming_meta.get("company", ""),
            "job_title": incoming_meta.get("job_title", ""),
            "match_score": incoming_meta.get("match_score", None),
            "hired": False,
            "pdf_filename": pdf_filename,
        }
        (hist_dir / "_meta.json").write_text(
            json.dumps(meta, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

        # Clean up pdflatex temp files
        for ext in (".tex", ".aux", ".log", ".out"):
            (PROJECT_ROOT / tex_name.replace(".tex", ext)).unlink(missing_ok=True)

    return FileResponse(
        path=str(stable_pdf),
        filename=pdf_filename,
        media_type="application/pdf",
    )


# ---------------------------------------------------------------------------
# History Routes
# ---------------------------------------------------------------------------


@app.get("/api/history/dashboard")
async def history_dashboard(page: int = 1, limit: int = 25):
    """Return paginated history entries, newest first."""
    entries = _scan_history_entries()
    total = len(entries)
    start = (page - 1) * limit
    return JSONResponse({
        "entries": entries[start: start + limit],
        "total": total,
        "page": page,
        "limit": limit,
    })


@app.post("/api/history/restore/{entry_id:path}")
async def history_restore(entry_id: str):
    """Return the resume_data.json for the given history entry."""
    entry_dir = (HISTORY_DIR / entry_id).resolve()
    if not str(entry_dir).startswith(str(HISTORY_DIR.resolve())):
        return JSONResponse(status_code=400, content={"error": "Invalid entry path"})

    data_file = entry_dir / "resume_data.json"
    if not data_file.exists():
        return JSONResponse(status_code=404, content={"error": "Entry not found"})
    return JSONResponse(json.loads(data_file.read_text(encoding="utf-8")))


@app.delete("/api/history/entry")
async def history_delete(request: Request):
    """Delete an entire history entry folder."""
    body = await request.json()
    folder = body.get("folder", "")
    if not folder:
        return JSONResponse(status_code=400, content={"error": "folder is required"})
    target = (HISTORY_DIR / folder).resolve()
    # Safety: must remain under HISTORY_DIR
    if not str(target).startswith(str(HISTORY_DIR.resolve())):
        return JSONResponse(status_code=400, content={"error": "Invalid folder path"})
    if not target.exists():
        return JSONResponse(status_code=404, content={"error": "Entry not found"})
    shutil.rmtree(str(target))
    return {"status": "ok"}


@app.patch("/api/history/hired")
async def history_hired(request: Request):
    """Toggle the hired status on a history entry."""
    body = await request.json()
    folder = body.get("folder", "")
    hired = body.get("hired", False)
    if not folder:
        return JSONResponse(status_code=400, content={"error": "folder is required"})
    meta_file = (HISTORY_DIR / folder / "_meta.json").resolve()
    if not str(meta_file).startswith(str(HISTORY_DIR.resolve())):
        return JSONResponse(status_code=400, content={"error": "Invalid folder path"})
    if not meta_file.exists():
        return JSONResponse(status_code=404, content={"error": "Entry not found"})
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    meta["hired"] = bool(hired)
    meta_file.write_text(json.dumps(meta, indent=4, ensure_ascii=False), encoding="utf-8")
    return {"status": "ok", "hired": meta["hired"]}


@app.get("/api/history/file/{file_path:path}")
async def history_file(file_path: str):
    """Serve a PDF file from the history directory."""
    target = (HISTORY_DIR / file_path).resolve()
    if not str(target).startswith(str(HISTORY_DIR.resolve())):
        return JSONResponse(status_code=400, content={"error": "Invalid path"})
    if not target.exists() or not target.suffix == ".pdf":
        return JSONResponse(status_code=404, content={"error": "File not found"})
    return FileResponse(path=str(target), media_type="application/pdf")


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
    from pipeline import resolve_ollama_model

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
    base_url = config.get("base_url", "").strip()
    
    # Allow Ollama without API key
    api_key = config.get("api_key", "").strip()
    if not api_key:
        env_key = "OPENROUTER_API_KEY" if provider == "openrouter_meta" else f"{provider.upper()}_API_KEY"
        api_key = os.getenv(env_key) or os.getenv("OPENAI_API_KEY")
    
    if provider == "ollama":
        # Ensure the custom base_url includes /v1 (Ollama's OpenAI-compatible path).
        # If the user left it blank, pipeline.py falls back to PROVIDER_CONFIGS which
        # already has /v1.  If they typed a URL, normalise it here.
        if base_url:
            base_url = base_url.rstrip("/")
            if not base_url.endswith("/v1"):
                base_url += "/v1"
        model = resolve_ollama_model(model)
    elif not api_key:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"API Key is required. Please provide it in the UI or set {env_key} / OPENAI_API_KEY environment variable."
            },
        )

    try:
        client = get_instructor_client({
            "provider": provider,
            "model": model,
            "base_url": base_url or "",
            "api_key": api_key
        })
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"error": f"Failed to create API client: {str(e)}"}
        )

    return StreamingResponse(
        run_pipeline(client, model, jd, data),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _resolve_provider_config(config: dict, import_os):
    """Shared helper: resolve provider, model, base_url, api_key from a config dict."""
    provider = config.get("provider", "openai")
    model = config.get("model", "gpt-4o-mini")
    base_url = config.get("base_url", "").strip()
    api_key = config.get("api_key", "").strip()

    if not api_key:
        env_key = (
            "OPENROUTER_API_KEY"
            if provider == "openrouter_meta"
            else f"{provider.upper()}_API_KEY"
        )
        api_key = import_os.getenv(env_key) or import_os.getenv("OPENAI_API_KEY")
    else:
        env_key = f"{provider.upper()}_API_KEY"

    return provider, model, base_url, api_key, env_key


@app.post("/api/cover-letter")
async def cover_letter_endpoint(request: Request):
    """
    Cover letter generation pipeline — streams SSE events.
    Accepts JD text, optional prior cover letter, provider config, and resume data.
    """
    import os
    from pipeline import (
        get_instructor_client,
        resolve_ollama_model,
        run_cover_letter_pipeline,
    )

    payload = await request.json()
    jd = payload.get("jd", "")
    prior_letter = payload.get("prior_letter", "")
    config = payload.get("config", {})
    data = payload.get("data", {})

    if not jd.strip():
        return JSONResponse(
            status_code=400, content={"error": "Job description is required."}
        )

    provider, model, base_url, api_key, env_key = _resolve_provider_config(config, os)

    if provider == "ollama":
        if base_url:
            base_url = base_url.rstrip("/")
            if not base_url.endswith("/v1"):
                base_url += "/v1"
        model = resolve_ollama_model(model)
    elif not api_key:
        return JSONResponse(
            status_code=400,
            content={
                "error": (
                    f"API Key is required. Please provide it in the UI or set "
                    f"{env_key} / OPENAI_API_KEY environment variable."
                )
            },
        )

    try:
        client = get_instructor_client(
            {
                "provider": provider,
                "model": model,
                "base_url": base_url or "",
                "api_key": api_key,
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to create API client: {str(e)}"},
        )

    return StreamingResponse(
        run_cover_letter_pipeline(
            client,
            model,
            jd,
            data,
            prior_letter if prior_letter and prior_letter.strip() else None,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Cover Letter History Routes
# ---------------------------------------------------------------------------


@app.post("/api/cl-history/save")
async def cl_history_save(request: Request):
    """Persist a generated cover letter to the CL history directory."""
    payload = await request.json()
    cl_data = payload.get("cover_letter", {})
    if not cl_data:
        return JSONResponse(status_code=400, content={"error": "cover_letter data required"})

    candidate_name = cl_data.get("candidate_name", "cover_letter")
    job_title = cl_data.get("job_title", "")
    company = cl_data.get("company", "")
    relevance = cl_data.get("relevance", None)

    safe_name = _safe_filename(candidate_name or "cover_letter")
    now = dt_obj.now()

    folder = (
        CL_HISTORY_DIR
        / now.strftime("%Y")
        / now.strftime("%m")
        / f"{now.strftime('%Y%m%d_%H%M%S')}_{safe_name}"
    )
    folder.mkdir(parents=True, exist_ok=True)

    entry_id = str(folder.relative_to(CL_HISTORY_DIR))

    # Build plain-text representation
    parts = [
        cl_data.get("subject_line", ""),
        "",
        cl_data.get("salutation", "Dear Hiring Manager,"),
        "",
        cl_data.get("opening_paragraph", ""),
    ]
    for para in cl_data.get("body_paragraphs", []):
        parts.extend(["", para])
    parts.extend(
        [
            "",
            cl_data.get("closing_paragraph", ""),
            "",
            cl_data.get("sign_off", "Sincerely,"),
            candidate_name,
        ]
    )
    plain_text = "\n".join(parts)

    (folder / "cover_letter.json").write_text(
        json.dumps(cl_data, indent=4, ensure_ascii=False), encoding="utf-8"
    )
    (folder / "cover_letter.txt").write_text(plain_text, encoding="utf-8")

    meta = {
        "id": entry_id,
        "timestamp": now.isoformat(timespec="seconds"),
        "candidate_name": candidate_name,
        "company": company,
        "job_title": job_title,
        "relevance_score": relevance,
    }
    (folder / "_meta.json").write_text(
        json.dumps(meta, indent=4, ensure_ascii=False), encoding="utf-8"
    )

    return {"status": "ok", "id": entry_id}


@app.get("/api/cl-history/dashboard")
async def cl_history_dashboard(page: int = 1, limit: int = 25):
    """Return paginated cover letter history entries, newest first."""
    entries = _scan_cl_history_entries()
    total = len(entries)
    start = (page - 1) * limit
    return JSONResponse(
        {
            "entries": entries[start : start + limit],
            "total": total,
            "page": page,
            "limit": limit,
        }
    )


@app.post("/api/cl-history/restore/{entry_id:path}")
async def cl_history_restore(entry_id: str):
    """Return the cover_letter.json for the given CL history entry."""
    data_file = CL_HISTORY_DIR / entry_id / "cover_letter.json"
    if not data_file.exists():
        return JSONResponse(status_code=404, content={"error": "Entry not found"})
    return JSONResponse(json.loads(data_file.read_text(encoding="utf-8")))


@app.get("/api/cl-history/file/{file_path:path}")
async def cl_history_file(file_path: str):
    """Serve a cover letter .txt file from the cl-history directory."""
    target = (CL_HISTORY_DIR / file_path).resolve()
    if not str(target).startswith(str(CL_HISTORY_DIR.resolve())):
        return JSONResponse(status_code=400, content={"error": "Invalid path"})
    if not target.exists() or target.suffix != ".txt":
        return JSONResponse(status_code=404, content={"error": "File not found"})
    return FileResponse(
        path=str(target), media_type="text/plain", filename=target.name
    )


@app.delete("/api/cl-history/entry")
async def cl_history_delete(request: Request):
    """Delete an entire cover letter history entry folder."""
    body = await request.json()
    folder = body.get("folder", "")
    if not folder:
        return JSONResponse(status_code=400, content={"error": "folder is required"})
    target = (CL_HISTORY_DIR / folder).resolve()
    if not str(target).startswith(str(CL_HISTORY_DIR.resolve())):
        return JSONResponse(status_code=400, content={"error": "Invalid folder path"})
    if not target.exists():
        return JSONResponse(status_code=404, content={"error": "Entry not found"})
    shutil.rmtree(str(target))
    return {"status": "ok"}
if __name__ == "__main__":
    if not HAS_PDFLATEX:
        print("\033[33m[WARNING] pdflatex not found. PDF generation will fail.\033[0m")
        print(
            "  Install: sudo apt install texlive-latex-base texlive-fonts-extra texlive-latex-extra"
        )
    uvicorn.run(app, host="127.0.0.1", port=7777)
