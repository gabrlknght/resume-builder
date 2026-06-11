"""Data I/O utilities for JSON files."""
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict:
    """Load a JSON file, return empty dict if missing."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_all_sections(section_files: dict, data_dir: Path) -> dict:
    """Load every section from data_dir into a single dict."""
    data = {}
    for section, filename in section_files.items():
        data[section] = load_json(data_dir / filename)
    return data


def save_json(path: Path, data: Any, ensure_newline: bool = False) -> None:
    """Save data to JSON file."""
    content = json.dumps(data, indent=4, ensure_ascii=False)
    if ensure_newline:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def save_all_sections(section_files: dict, data_dir: Path, payload: dict) -> None:
    """Save all sections to disk from payload."""
    for section, filename in section_files.items():
        section_data = payload.get(section, {})
        save_json(data_dir / filename, section_data, ensure_newline=True)
