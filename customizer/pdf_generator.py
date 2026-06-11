"""PDF generation utilities for resumes."""
import subprocess
import sys
import tempfile
from pathlib import Path

from config import PDF_TEMP_EXTS, PDF_TEMP_TEX_NAME, PROJECT_ROOT, RENDER_SCRIPT
from data_utils import save_json


class PDFGenerationError(Exception):
    """Raised when PDF generation fails."""
    pass


def render_tex_from_data(
    section_files: dict,
    section_data: dict,
    output_tex_name: str = PDF_TEMP_TEX_NAME,
) -> Path:
    """Render resume.tex from JSON data using render_resume.py."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Write payload sections to temp JSON files
        for section, filename in section_files.items():
            data = section_data.get(section, {})
            save_json(tmp / filename, data)

        # Run render_resume.py
        result = subprocess.run(
            [
                sys.executable,
                str(RENDER_SCRIPT),
                "--data-dir",
                str(tmp),
                "--output",
                output_tex_name,
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )

        tex_file = PROJECT_ROOT / output_tex_name
        if result.returncode != 0 or not tex_file.exists():
            raise PDFGenerationError(
                f"Template rendering failed: {result.stderr or result.stdout}"
            )

        return tex_file


def compile_pdf_from_tex(tex_name: str) -> Path:
    """Compile .tex to PDF using pdflatex."""
    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", tex_name],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    pdf_file = PROJECT_ROOT / tex_name.replace(".tex", ".pdf")
    if not pdf_file.exists():
        # Clean up .tex
        (PROJECT_ROOT / tex_name).unlink(missing_ok=True)
        raise PDFGenerationError(
            f"PDF compilation failed: {result.stdout[-2000:]}"
        )

    return pdf_file


def cleanup_tex_files(tex_name: str) -> None:
    """Clean up temporary LaTeX files."""
    base_name = tex_name.replace(".tex", "")
    for ext in PDF_TEMP_EXTS:
        (PROJECT_ROOT / f"{base_name}{ext}").unlink(missing_ok=True)


def generate_pdf(
    section_files: dict,
    section_data: dict,
    tex_name: str = PDF_TEMP_TEX_NAME,
) -> Path:
    """Full PDF generation pipeline: render TeX, compile, cleanup."""
    try:
        render_tex_from_data(section_files, section_data, tex_name)
        pdf_file = compile_pdf_from_tex(tex_name)
        return pdf_file
    finally:
        cleanup_tex_files(tex_name)
