"""Configuration and constants for the Resume Customizer server."""
import shutil
from pathlib import Path

# Paths
CUSTOMIZER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CUSTOMIZER_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
RENDER_SCRIPT = PROJECT_ROOT / "scripts" / "render_resume.py"

STATIC_DIR = CUSTOMIZER_DIR / "static"
USE_MINIFIED = (STATIC_DIR / "app.min.js").exists()

HISTORY_DIR = DATA_DIR / "history"
CL_HISTORY_DIR = DATA_DIR / "cl-history"

# Section file mappings
SECTION_FILES = {
    "profile": "profile.json",
    "contact": "contact.json",
    "education": "education.json",
    "experience": "experience.json",
    "projects": "projects.json",
    "skills": "skills.json",
}

# PDF generation
HAS_PDFLATEX = shutil.which("pdflatex") is not None

# File extensions
PDF_TEMP_TEX_NAME = "_customizer_tmp.tex"
PDF_TEMP_EXTS = (".tex", ".aux", ".log", ".out")
