# customizer/server_additions.py

from datetime import datetime as dt_obj, timedelta
import json
from pathlib import Path

from fastapi.responses import JSONResponse

# Mirror path constants from server.py to avoid a circular import (no __init__.py
# in this package, so relative imports are not available).
_CUSTOMIZER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CUSTOMIZER_DIR.parent
_DATA_DIR = _PROJECT_ROOT / "data"
HISTORY_DIR = _DATA_DIR / "history"
CL_HISTORY_DIR = _DATA_DIR / "cl-history"

_PERIOD_WINDOWS = {
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "annual": timedelta(days=365),
}


def _scan_entries(history_dir: Path, entry_type: str) -> list:
    """Walk a history directory for _meta.json files and tag each with type."""
    entries = []
    if not history_dir.exists():
        return entries
    for meta_file in history_dir.rglob("_meta.json"):
        try:
            entry = json.loads(meta_file.read_text(encoding="utf-8"))
            entry["_type"] = entry_type
            entries.append(entry)
        except Exception:
            continue
    return entries


def _aggregate_history(period: str, entry_type: str = "all") -> dict:
    """Return aggregated submission statistics for the given period and type.

    Parameters
    ----------
    period : str
        One of ``"weekly"``, ``"monthly"``, or ``"annual"``.
        Filters to the last 7 / 30 / 365 days respectively and buckets by
        day / ISO-week / calendar-month.
    entry_type : str
        One of ``"resume"``, ``"cover_letter"``, or ``"all"``.
    """
    if period not in _PERIOD_WINDOWS:
        return {"error": "Invalid period"}

    cutoff = dt_obj.now() - _PERIOD_WINDOWS[period]

    entries = []
    if entry_type in ("resume", "all"):
        entries.extend(_scan_entries(HISTORY_DIR, "resume"))
    if entry_type in ("cover_letter", "all"):
        entries.extend(_scan_entries(CL_HISTORY_DIR, "cover_letter"))

    # Filter to the relevant window and parse timestamps up front.
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
        else:  # weekly
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

        series.append(
            {
                "label": label,
                "total": subcnt,
                "hired": hiredcnt,
                "pending": pendingcnt,
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


def add_stats_routes(app):
    @app.get("/api/history/stats")
    async def history_stats(period: str = "annual", type: str = "all"):
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
