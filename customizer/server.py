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
from datetime import datetime as dt_obj
from datetime import timedelta
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
    finish_resume_history_entry,
    restore_cl_history_entry,
    restore_history_entry,
    save_cover_letter_history,
    scan_history_entries,
    start_resume_history_entry,
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
# Serve models.ini to the frontend
# ---------------------------------------------------------------------------
@app.get("/api/llama-cpp-models")
def get_llama_cpp_models():
    """Return available llama.cpp model aliases from ~/models.ini."""
    import configparser
    import os

    ini_path = Path(os.path.expanduser("~/models.ini"))
    models = []
    if ini_path.exists():
        cfg = configparser.ConfigParser()
        cfg.read(ini_path)
        models = [s for s in cfg.sections()]
    return {"models": models}


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

    # Reserve a history folder/path, but don't write metadata until the PDF
    # actually lands there — otherwise a failed move leaves a ghost entry.
    profile = payload.get("profile", {})
    profile_name = profile.get("name", "resume")
    entry_id, hist_folder, pdf_path, entry_now = start_resume_history_entry(
        HISTORY_DIR, profile_name
    )

    # Move the PDF into place and write its history metadata as one unit: if
    # either step fails, wipe the whole (still-uncommitted) hist_folder rather
    # than leave a partial file or an orphaned PDF with no metadata behind.
    try:
        shutil.move(str(pdf_file), str(pdf_path))
        finish_resume_history_entry(
            hist_folder=hist_folder,
            entry_id=entry_id,
            payload=payload,
            profile_name=profile_name,
            pdf_path=pdf_path,
            now=entry_now,
            company=incoming_meta.get("company", ""),
            job_title=incoming_meta.get("job_title", ""),
            match_score=incoming_meta.get("match_score"),
            timing=incoming_meta.get("timing"),
            model=incoming_meta.get("model", ""),
            provider=incoming_meta.get("provider", ""),
        )
    except (OSError, ValueError, TypeError) as e:
        shutil.rmtree(str(hist_folder), ignore_errors=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to save PDF to history: {str(e)}"},
        )

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
        return JSONResponse(status_code=400, content={"error": "Job description is required."})

    provider = config.get("provider", "openai")
    model = config.get("model", "gpt-4o-mini")
    base_url = config.get("base_url", "").strip()
    api_key = config.get("api_key", "").strip()
    tone = payload.get("tone", config.get("tone", "professional"))

    # Resolve API key from environment if not provided
    if not api_key:
        env_key = (
            "OPENROUTER_API_KEY" if provider == "openrouter_meta" else f"{provider.upper()}_API_KEY"
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
        run_pipeline(client, model, jd, data, tone, provider),
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
    extra_facts = payload.get("extra_facts", "")
    config = payload.get("config", {})
    data = payload.get("data", {})

    if not jd.strip():
        return JSONResponse(status_code=400, content={"error": "Job description is required."})

    provider = config.get("provider", "openai")
    model = config.get("model", "gpt-4o-mini")
    base_url = config.get("base_url", "").strip()
    api_key = config.get("api_key", "").strip()
    tone = payload.get("tone", config.get("tone", "professional"))

    # Resolve API key from environment if not provided
    if not api_key:
        env_key = (
            "OPENROUTER_API_KEY" if provider == "openrouter_meta" else f"{provider.upper()}_API_KEY"
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
            provider,
            extra_facts if extra_facts and extra_facts.strip() else None,
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

    try:
        entry_id = save_cover_letter_history(CL_HISTORY_DIR, cl_data)
    except (OSError, ValueError, TypeError) as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to save cover letter history: {str(e)}"},
        )
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
    return FileResponse(path=str(target), media_type="text/plain", filename=target.name)


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
# Stats Routes
# ---------------------------------------------------------------------------
_PERIOD_WINDOWS = {
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "annual": timedelta(days=365),
}


def _scan_entries_with_type(history_dir, entry_type: str) -> list:
    entries = scan_history_entries(history_dir)
    for entry in entries:
        entry["_type"] = entry_type
    return entries


def _aggregate_history(period: str, entry_type: str = "all") -> dict:
    if period not in _PERIOD_WINDOWS:
        return {"error": "Invalid period"}

    cutoff = dt_obj.now() - _PERIOD_WINDOWS[period]
    entries = []
    if entry_type in ("resume", "all"):
        entries.extend(_scan_entries_with_type(HISTORY_DIR, "resume"))
    if entry_type in ("cover_letter", "all"):
        entries.extend(_scan_entries_with_type(CL_HISTORY_DIR, "cover_letter"))

    timed = []
    for e in entries:
        try:
            ts = dt_obj.fromisoformat(e["timestamp"])
        except (KeyError, ValueError):
            continue
        if ts >= cutoff:
            timed.append((ts, e))

    timed.sort(key=lambda x: x[0], reverse=True)

    bucketed: dict = {}
    for ts, e in timed:
        if period == "annual":
            key = f"{ts.year}-{ts.month:02d}"
        elif period == "monthly":
            key = f"{ts.year}-W{ts.isocalendar()[1]:02d}"
        else:
            key = ts.strftime("%Y-%m-%d")
        bucketed.setdefault(key, []).append(e)

    series = []
    total_submissions = hired_total = pending_total = 0

    for label in sorted(bucketed.keys()):
        bucket = bucketed[label]
        subcnt = len(bucket)
        hiredcnt = sum(1 for item in bucket if item.get("hired"))
        pendingcnt = subcnt - hiredcnt

        total_submissions += subcnt
        hired_total += hiredcnt
        pending_total += pendingcnt

        rates = []
        durations = []
        for item in bucket:
            timing = item.get("timing")
            if not timing:
                continue
            secs = timing.get("elapsed_seconds")
            tokens = timing.get("total_tokens")
            if secs and tokens:
                rates.append(tokens / secs)
            if secs:
                durations.append(secs)
        avg_tok_per_sec = round(sum(rates) / len(rates), 1) if rates else None
        avg_elapsed_seconds = round(sum(durations) / len(durations), 1) if durations else None

        series.append(
            {
                "label": label,
                "total": subcnt,
                "hired": hiredcnt,
                "pending": pendingcnt,
                "avg_tokens_per_sec": avg_tok_per_sec,
                "avg_elapsed_seconds": avg_elapsed_seconds,
            }
        )

    return {
        "period": period,
        "type": entry_type,
        "submission_count": total_submissions,
        "hired_count": hired_total,
        "pending_count": pending_total,
        "series": series,
    }


@app.get("/api/history/stats")
async def history_stats(period: str = "weekly", type: str = "all"):
    if period not in _PERIOD_WINDOWS:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid period. Use weekly, monthly, or annual."},
        )
    if type not in ("resume", "cover_letter", "all"):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid type. Use resume, cover_letter, or all."},
        )
    return JSONResponse(_aggregate_history(period, type))


if __name__ == "__main__":
    if not HAS_PDFLATEX:
        print("\033[33m[WARNING] pdflatex not found. PDF generation will fail.\033[0m")
        print(
            "  Install: sudo apt install texlive-latex-base texlive-fonts-extra texlive-latex-extra"
        )
    uvicorn.run(app, host="127.0.0.1", port=7777)
