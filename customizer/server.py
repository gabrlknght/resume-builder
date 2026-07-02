#!/usr/bin/env python3
"""
Resume Customizer — FastAPI backend.

Serves a Jinja2-templated editor UI, accepts JSON payloads to generate PDFs
or persist data back to disk.

Usage:
    python customizer/server.py
"""

import shutil
import sys
from pathlib import Path

# Ensure customizer/ is on sys.path so `from pipeline import ...` works
_CUSTOMIZER_DIR = Path(__file__).resolve().parent
if str(_CUSTOMIZER_DIR) not in sys.path:
    sys.path.insert(0, str(_CUSTOMIZER_DIR))

import uvicorn
from config import (
    CL_HISTORY_DIR,
    CUSTOMIZER_DIR,
    DATA_DIR,
    HAS_PDFLATEX,
    HISTORY_DIR,
    SECTION_FILES,
    USE_MINIFIED,
)
from data_utils import load_all_sections, save_all_sections
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from history_manager import (
    delete_history_entry,
    restore_cl_history_entry,
    restore_history_entry,
    save_cover_letter_history,
    save_resume_history,
    scan_history_entries,
    update_hired_status,
)
from pdf_generator import PDFGenerationError, generate_pdf

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------
app = FastAPI(title="Resume Customizer")
app.mount("/static", StaticFiles(directory=CUSTOMIZER_DIR / "static"), name="static")
templates = Jinja2Templates(directory=CUSTOMIZER_DIR / "templates")


# ---------------------------------------------------------------------------
# Index / Main Page
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the customizer page with forms pre-populated from JSON."""
    data = load_all_sections(SECTION_FILES, DATA_DIR)
    import json
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "data": data,
            "data_json": json.dumps(data),
            "use_minified": USE_MINIFIED,
        },
    )


# ---------------------------------------------------------------------------
# PDF Generation
# ---------------------------------------------------------------------------
@app.post("/api/generate")
async def generate(request: Request):
    """Accept JSON payload, generate PDF, stream it back."""
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

    try:
        pdf_file = generate_pdf(SECTION_FILES, payload)
    except PDFGenerationError as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    # Save to history
    profile = payload.get("profile", {})
    profile_name = profile.get("name", "resume")
    entry_id, pdf_path = save_resume_history(
        HISTORY_DIR,
        payload,
        profile_name,
        company=incoming_meta.get("company", ""),
        job_title=incoming_meta.get("job_title", ""),
        match_score=incoming_meta.get("match_score"),
        timing=incoming_meta.get("timing"),
    )

    # Move generated PDF to history folder
    shutil.move(str(pdf_file), str(pdf_path))

    # Return PDF with correct filename
    return FileResponse(
        path=str(pdf_path),
        filename=pdf_path.name,
        media_type="application/pdf",
    )


# ---------------------------------------------------------------------------
# Data Persistence
# ---------------------------------------------------------------------------
@app.post("/api/save")
async def save(request: Request):
    """Overwrite the on-disk JSON files with the provided payload."""
    payload = await request.json()
    save_all_sections(SECTION_FILES, DATA_DIR, payload)
    return {"status": "ok", "message": "All data saved to disk."}


# ---------------------------------------------------------------------------
# Resume History Routes
# ---------------------------------------------------------------------------
@app.get("/api/history/dashboard")
async def history_dashboard(page: int = 1, limit: int = 25):
    """Return paginated history entries, newest first."""
    entries = scan_history_entries(HISTORY_DIR)
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


@app.post("/api/history/restore/{entry_id:path}")
async def history_restore(entry_id: str):
    """Return the resume_data.json for the given history entry."""
    try:
        data = restore_history_entry(HISTORY_DIR, entry_id)
        return JSONResponse(data)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid entry path"})
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Entry not found"})


@app.delete("/api/history/entry")
async def history_delete(request: Request):
    """Delete an entire history entry folder."""
    body = await request.json()
    folder = body.get("folder", "")
    if not folder:
        return JSONResponse(status_code=400, content={"error": "folder is required"})

    try:
        delete_history_entry(HISTORY_DIR, folder)
        return {"status": "ok"}
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid folder path"})
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Entry not found"})


@app.patch("/api/history/hired")
async def history_hired(request: Request):
    """Toggle the hired status on a history entry."""
    body = await request.json()
    folder = body.get("folder", "")
    hired = body.get("hired", False)
    if not folder:
        return JSONResponse(status_code=400, content={"error": "folder is required"})

    try:
        new_status = update_hired_status(HISTORY_DIR, folder, hired)
        return {"status": "ok", "hired": new_status}
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid folder path"})
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Entry not found"})


@app.get("/api/history/file/{file_path:path}")
async def history_file(file_path: str):
    """Serve a PDF file from the history directory."""
    target = (HISTORY_DIR / file_path).resolve()
    if not str(target).startswith(str(HISTORY_DIR.resolve())):
        return JSONResponse(status_code=400, content={"error": "Invalid path"})
    if not target.exists() or target.suffix != ".pdf":
        return JSONResponse(status_code=404, content={"error": "File not found"})
    return FileResponse(path=str(target), media_type="application/pdf")


# ---------------------------------------------------------------------------
# AI Tailoring Routes
# ---------------------------------------------------------------------------
@app.post("/api/tailor")
async def tailor(request: Request):
    """Multi-stage tailoring pipeline — streams SSE events."""
    import os

    from pipeline import get_instructor_client, resolve_ollama_model, run_pipeline

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
    api_key = config.get("api_key", "").strip()
    tone = payload.get("tone", config.get("tone", "professional"))

    # Resolve API key from environment if not provided
    if not api_key:
        env_key = (
            "OPENROUTER_API_KEY"
            if provider == "openrouter_meta"
            else f"{provider.upper()}_API_KEY"
        )
        api_key = os.getenv(env_key) or os.getenv("OPENAI_API_KEY")

    # Ollama-specific setup
    if provider == "ollama":
        if base_url:
            base_url = base_url.rstrip("/")
            if not base_url.endswith("/v1"):
                base_url += "/v1"
        model = resolve_ollama_model(model)
    # llama.cpp: no /v1 normalization (frontend handles it), no API key required
    elif provider == "llamacpp":
        pass
    elif not api_key:
        return JSONResponse(
            status_code=400,
            content={
                "error": "API Key is required. Please provide it in the UI or set the appropriate environment variable."
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
            status_code=500, content={"error": f"Failed to create API client: {str(e)}"}
        )

    return StreamingResponse(
        run_pipeline(client, model, jd, data, tone),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Cover Letter Routes
# ---------------------------------------------------------------------------
@app.post("/api/cover-letter")
async def cover_letter_endpoint(request: Request):
    """Cover letter generation pipeline — streams SSE events."""
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

    provider = config.get("provider", "openai")
    model = config.get("model", "gpt-4o-mini")
    base_url = config.get("base_url", "").strip()
    api_key = config.get("api_key", "").strip()
    tone = payload.get("tone", config.get("tone", "professional"))

    # Resolve API key from environment if not provided
    if not api_key:
        env_key = (
            "OPENROUTER_API_KEY"
            if provider == "openrouter_meta"
            else f"{provider.upper()}_API_KEY"
        )
        api_key = os.getenv(env_key) or os.getenv("OPENAI_API_KEY")

    # Ollama-specific setup
    if provider == "ollama":
        if base_url:
            base_url = base_url.rstrip("/")
            if not base_url.endswith("/v1"):
                base_url += "/v1"
        model = resolve_ollama_model(model)
    # llama.cpp: no /v1 normalization (frontend handles it), no API key required
    elif provider == "llamacpp":
        pass
    elif not api_key:
        return JSONResponse(
            status_code=400,
            content={
                "error": "API Key is required. Please provide it in the UI or set the appropriate environment variable."
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
            tone,
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

    entry_id = save_cover_letter_history(CL_HISTORY_DIR, cl_data)
    return {"status": "ok", "id": entry_id}


@app.get("/api/cl-history/dashboard")
async def cl_history_dashboard(page: int = 1, limit: int = 25):
    """Return paginated cover letter history entries, newest first."""
    entries = scan_history_entries(CL_HISTORY_DIR)
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
    try:
        data = restore_cl_history_entry(CL_HISTORY_DIR, entry_id)
        return JSONResponse(data)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid entry path"})
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Entry not found"})


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

    try:
        delete_history_entry(CL_HISTORY_DIR, folder)
        return {"status": "ok"}
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid folder path"})
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Entry not found"})


# ---------------------------------------------------------------------------
# Stats Routes (defined in server_additions.py)
# ---------------------------------------------------------------------------
from server_additions import add_stats_routes  # noqa: E402

add_stats_routes(app)


if __name__ == "__main__":
    if not HAS_PDFLATEX:
        print("\033[33m[WARNING] pdflatex not found. PDF generation will fail.\033[0m")
        print(
            "  Install: sudo apt install texlive-latex-base texlive-fonts-extra texlive-latex-extra"
        )
    uvicorn.run(app, host="127.0.0.1", port=7777)
