"""History management for resume and cover letter saves."""
import json
import re
import shutil
from datetime import datetime as dt_obj
from pathlib import Path
from typing import Optional

from data_utils import load_json, save_json


def safe_filename(name: str) -> str:
    """Turn a display name into a filename-safe string."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()


def get_history_folder(history_base: Path, dt: dt_obj, safe_name: str) -> Path:
    """Return (and create) the timestamped folder for a history entry."""
    ts = dt.strftime("%Y%m%d_%H%M%S")
    folder = history_base / dt.strftime("%Y") / dt.strftime("%m") / f"{ts}_{safe_name}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def scan_history_entries(history_dir: Path) -> list:
    """Walk history_dir for _meta.json files and return list sorted newest-first."""
    entries = []
    if not history_dir.exists():
        return entries
    for meta_file in history_dir.rglob("_meta.json"):
        try:
            entries.append(load_json(meta_file))
        except (json.JSONDecodeError, OSError):
            continue
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries


def save_resume_history(
    history_dir: Path,
    payload: dict,
    profile_name: str,
    company: str = "",
    job_title: str = "",
    match_score: Optional[float] = None,
) -> tuple[str, Path]:
    """Save resume to history with metadata. Returns (entry_id, pdf_path)."""
    safe_name = safe_filename(profile_name)
    now = dt_obj.now()
    hist_folder = get_history_folder(history_dir, now, safe_name)

    # Save resume data snapshot
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    save_json(hist_folder / "resume_data.json", payload)

    # Save metadata
    entry_id = str(hist_folder.relative_to(history_dir))
    meta = {
        "id": entry_id,
        "timestamp": now.isoformat(timespec="seconds"),
        "profile_name": profile_name,
        "company": company,
        "job_title": job_title,
        "match_score": match_score,
        "hired": False,
        "pdf_filename": f"{safe_name}_{ts_str}.pdf",
    }
    save_json(hist_folder / "_meta.json", meta)

    return entry_id, hist_folder / meta["pdf_filename"]


def save_cover_letter_history(
    cl_history_dir: Path,
    cl_data: dict,
) -> str:
    """Save cover letter to history. Returns entry_id."""
    candidate_name = cl_data.get("candidate_name", "cover_letter")
    job_title = cl_data.get("job_title", "")
    company = cl_data.get("company", "")
    relevance = cl_data.get("relevance", None)

    safe_name = safe_filename(candidate_name)
    now = dt_obj.now()

    folder = get_history_folder(cl_history_dir, now, safe_name)
    entry_id = str(folder.relative_to(cl_history_dir))

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

    # Save files
    save_json(folder / "cover_letter.json", cl_data)
    (folder / "cover_letter.txt").write_text(plain_text, encoding="utf-8")

    meta = {
        "id": entry_id,
        "timestamp": now.isoformat(timespec="seconds"),
        "candidate_name": candidate_name,
        "company": company,
        "job_title": job_title,
        "relevance_score": relevance,
    }
    save_json(folder / "_meta.json", meta)

    return entry_id


def restore_history_entry(history_dir: Path, entry_id: str) -> dict:
    """Load resume_data.json for a history entry."""
    entry_dir = (history_dir / entry_id).resolve()
    if not str(entry_dir).startswith(str(history_dir.resolve())):
        raise ValueError("Invalid entry path")

    data_file = entry_dir / "resume_data.json"
    if not data_file.exists():
        raise FileNotFoundError("Entry not found")
    return load_json(data_file)


def restore_cl_history_entry(cl_history_dir: Path, entry_id: str) -> dict:
    """Load cover_letter.json for a CL history entry."""
    entry_dir = (cl_history_dir / entry_id).resolve()
    if not str(entry_dir).startswith(str(cl_history_dir.resolve())):
        raise ValueError("Invalid entry path")

    data_file = entry_dir / "cover_letter.json"
    if not data_file.exists():
        raise FileNotFoundError("Entry not found")
    return load_json(data_file)


def delete_history_entry(history_dir: Path, folder: str) -> None:
    """Delete an entire history entry folder."""
    target = (history_dir / folder).resolve()
    if not str(target).startswith(str(history_dir.resolve())):
        raise ValueError("Invalid folder path")
    if not target.exists():
        raise FileNotFoundError("Entry not found")
    shutil.rmtree(str(target))


def update_hired_status(history_dir: Path, folder: str, hired: bool) -> bool:
    """Toggle the hired status on a history entry."""
    meta_file = (history_dir / folder / "_meta.json").resolve()
    if not str(meta_file).startswith(str(history_dir.resolve())):
        raise ValueError("Invalid folder path")
    if not meta_file.exists():
        raise FileNotFoundError("Entry not found")

    meta = load_json(meta_file)
    meta["hired"] = bool(hired)
    save_json(meta_file, meta)
    return meta["hired"]
