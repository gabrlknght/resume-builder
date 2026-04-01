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
import tempfile
import shutil
import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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
                "--data-dir", str(tmp),
                "--output", tex_name,
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        tex_file = PROJECT_ROOT / tex_name
        if result.returncode != 0 or not tex_file.exists():
            return JSONResponse(
                status_code=500,
                content={"error": "Template rendering failed", "details": result.stderr or result.stdout},
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
                content={"error": "PDF compilation failed", "details": result.stdout[-2000:]},
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


PROVIDER_CONFIGS = {
    "cerebras": {"base_url": "https://api.cerebras.ai/v1"},
    "nvidia": {"base_url": "https://integrate.api.nvidia.com/v1"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
    "openai": {"base_url": None},
}

@app.post("/api/tailor")
async def tailor(request: Request):
    """
    Accept JD and Resume JSON payload, call LLM to tailor the profile/experience/projects.
    Returns the newly tailored JSON objects.
    """
    import os
    try:
        import openai
    except ImportError:
        return JSONResponse(
            status_code=500,
            content={"error": "openai module not installed. Run: pip install openai"}
        )

    payload = await request.json()
    jd = payload.get("jd", "")
    config = payload.get("config", {})
    data = payload.get("data", {})

    provider = config.get("provider", "openai")
    model = config.get("model", "gpt-4o-mini")
    base_url = config.get("base_url", "").strip()
    api_key = config.get("api_key", "").strip()

    if not base_url:
        base_url = PROVIDER_CONFIGS.get(provider, {}).get("base_url")
        
    if not api_key:
        env_key = f"{provider.upper()}_API_KEY"
        api_key = os.getenv(env_key) or os.getenv("OPENAI_API_KEY")
        
    if not api_key:
        return JSONResponse(status_code=400, content={"error": f"API Key is required. Please provide it in the UI or set {env_key} / OPENAI_API_KEY environment variable."})

    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    skill_path = CUSTOMIZER_DIR / "TAILOR_SKILL.md"
    skill_instructions = skill_path.read_text(encoding="utf-8") if skill_path.exists() else "Tailor the resume to the JD."

    prompt = f"""
{skill_instructions}

You are an expert technical resume writer. Given the user's current resume data (JSON) and a target Job Description, tailor the resume to the job description.

Specifically, you should update:
1. The `profile` section (especially the `bio` and perhaps `title`).
2. The `experience` section (rephrase and enhance `details` bullet points with relevant keywords from the JD without fabricating experience).
3. The `projects` section (rephrase `description` and `technologies`).
4. Rate the relevance of the user's resume to the JD on a scale of 1-10.
5. Provide a brief gap analysis explaining exactly what the resume lacks compared to the JD.

CRITICAL INSTRUCTIONS TO PREVENT DATA CORRUPTION & AI SLOP:
- You MUST preserve the EXACT JSON structure, arrays, and keys of the input.
- DO NOT delete, alter, or corrupt ANY metadata fields (e.g. `startDate`, `endDate`, `location`, `company`, `role`, `logo`, `liveUrl`, etc.). Keep them exactly as they are.
- DO NOT write any meta-commentary, thoughts, notes, or explanations (like "Rephrased to emphasize use of Next.js") inside the output text fields!
- Provide ONLY the final, polished, rephrased content for the `bio`, `details`, and `description` strings.

DO NOT return anything other than a valid JSON object. 
Ensure the returned JSON has EXACTLY five keys: "profile", "experience", "projects", "relevance" (integer 1-10), and "relevance_analysis" (string summary).

Job Description:
{jd[-6000:]}

Current Resume Data:
{json.dumps({
    "profile": data.get("profile", {}),
    "experience": data.get("experience", {}).get("experience", []),
    "projects": data.get("projects", {}).get("projects", [])
}, indent=2)}

Return ONLY a raw JSON string mapping to those 5 keys. DO NOT wrap with ```json or markdown tags.
"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert AI recruiter and resume writer. Respond strictly with raw valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith("```json"):
            result_text = result_text[7:-3].strip()
        elif result_text.startswith("```"):
            result_text = result_text[3:-3].strip()
            
        tailored_json = json.loads(result_text)
        
        # Format lists back to dict wrapper expected by frontend state
        if isinstance(tailored_json.get("experience"), list):
            tailored_json["experience"] = {"experience": tailored_json["experience"]}
        if isinstance(tailored_json.get("projects"), list):
            tailored_json["projects"] = {"projects": tailored_json["projects"]}
            
        return tailored_json

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"LLM Generation Failed: {{str(e)}}"})

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not HAS_PDFLATEX:
        print("\033[33m[WARNING] pdflatex not found. PDF generation will fail.\033[0m")
        print("  Install: sudo apt install texlive-latex-base texlive-fonts-extra texlive-latex-extra")
    uvicorn.run(app, host="127.0.0.1", port=8000)
