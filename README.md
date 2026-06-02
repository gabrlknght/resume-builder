# Automated Resume Builder

Manage your professional profile via JSON and get a high-quality LaTeX resume PDF automatically. 

Two workflows available:
- **CI/CD (Zero Setup)**: Push to GitHub → PDF auto-generated. No local installation required.
- **Local Web UI (Power User)**: Edit JSON visually, preview PDF in real-time, generate on-demand with full local control.

[**📄 View Sample Resume**](https://github.com/jangwanAnkit/resume-builder/releases/download/latest/resume.pdf)

## Quick Start

### Option A: CI/CD Only (No Local Setup)
1. **Use as Template / Fork**: Click the **"Use this template"** button.
2. Edit JSON files in `data/`.
3. Push to `main` → GitHub Actions auto-generates PDF.
4. Download from [**Latest Release**](https://github.com/jangwanAnkit/resume-builder/releases/download/latest/resume.pdf).

### Option B: Local Web UI (Recommended for Power Users)
1. **Run the installer** (handles all dependencies):
   ```bash
   bash install.sh
   ```
2. **Run the customizer**:
   ```bash
   uv run python customizer/server.py  # or: python3 customizer/server.py
   ```
3. Open [http://localhost:7777](http://localhost:7777).

> **Manual dependency install** (if you prefer step-by-step):
> ```bash
> uv pip install -r requirements.txt
> sudo apt install texlive-latex-base texlive-fonts-extra texlive-latex-extra
> ```

![Resume Customizer UI](docs/pdf_preview_final.png)

## Features

- **Local Web UI**: A minimalist, built-in Customizer UI lets you edit JSON data effortlessly and preview the generated PDF in real-time.
- **AI-Tailored Resumes (Multi-Stage Pipeline)**: Tailor your resume to any job description using a 4-stage pipeline — JD Analysis, Match & Score, Section Tailoring, and Validation. Supports OpenAI, OpenRouter, Cerebras, Gemini, NVIDIA, and **local models via Ollama** with BYOK. Streams real-time progress via SSE, shows visual diffs, relevance scoring, and evaluation metrics (alignment, content preservation, hallucination detection).
- **Local LLM Support**: Run the tailoring pipeline entirely offline using [Ollama](https://ollama.com) — no API key required.
- **JSON-based Source of Truth**: Manage all your data (profile, experience, education, skills, projects) in structured JSON files.
- **LaTeX Professionalism**: Utilizes a professional LaTeX template with Jinja2 rendering for a premium look.
- **Automated CI/CD**: GitHub Actions automatically compiles your LaTeX source into a PDF on every push to `main`.
- **Evaluation Framework**: Built-in `eval-module` with Pydantic schemas, quality metrics (alignment, preservation, hallucination detection), and golden test cases for regression testing.

## Server Configuration

The customizer server binds to `127.0.0.1:7777` by default.

**Change host or port** by running `uvicorn` directly instead of the script:
```bash
uv run uvicorn customizer.server:app --host 0.0.0.0 --port 8080 --reload
```

| Setting | Default | Notes |
|---|---|---|
| Host | `127.0.0.1` | Use `0.0.0.0` to expose on your network |
| Port | `7777` | Change with `--port <number>` |

## AI Tailoring — Supported Providers

Open the **"Tailor with AI"** panel in the UI and select your provider. The base URL auto-fills; only the API key field is required for cloud providers.

| Provider | Requires API Key | Default Model | Notes |
|---|---|---|---|
| **OpenAI** | Yes | `gpt-4o-mini` | Set `OPENAI_API_KEY` env var to skip UI entry |
| **Cerebras** | Yes | `llama3.1-8b` | Fast inference |
| **NVIDIA NIM** | Yes | `moonshotai/kimi-k2.5` | |
| **Gemini** | Yes | `gemini-2.5-flash` | |
| **OpenRouter** | Yes | `openrouter/free` | Many free models available |
| **OpenRouter (Meta)** | Yes | `meta-llama/llama-3.3-70b-instruct:free` | Free Llama 3.3 70B |
| **Ollama (Local)** | **No** | `gemma4:e4b` | Fully offline, no key needed |
| **Custom** | Optional | *(enter manually)* | Any OpenAI-compatible endpoint |

### Environment Variables (Cloud Providers)

Set an API key as an environment variable to avoid pasting it into the UI every time:

```bash
export OPENAI_API_KEY="sk-..."
export CEREBRAS_API_KEY="..."
export GEMINI_API_KEY="..."
export NVIDIA_API_KEY="..."
export OPENROUTER_API_KEY="..."
```

The server reads `<PROVIDER>_API_KEY` (e.g. `CEREBRAS_API_KEY`) and falls back to `OPENAI_API_KEY` if not set.

## Local LLM with Ollama

Run the entire tailoring pipeline **100% offline** — no API key, no internet required.

### Setup

1. **Install Ollama**: visit [https://ollama.com](https://ollama.com) or run:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```
2. **Pull a model** (the installer handles this if you choose to):
   ```bash
   ollama pull gemma4:e4b     # Recommended — best quality
   ollama pull llama3.2       # Lightweight fallback
   ollama pull lfm2.5:latest  # Liquid Foundation Model
   ```
3. **Start the Ollama daemon** (auto-starts on most systems; run manually if needed):
   ```bash
   ollama serve
   ```
4. Select **"Ollama (Local)"** in the UI — no API key needed.

### Ollama Host & Port

The default Ollama endpoint is `http://localhost:11434`. If you run Ollama on a different host or port, update the **Base URL** field in the UI:

```
http://<your-ollama-host>:<port>
```

The backend automatically appends `/v1` to construct the OpenAI-compatible path, so you only need to enter the base address (e.g. `http://192.168.1.10:11434`).

### Supported Models & Aliases

The following short-name aliases are recognized in the **Model** field:

| Alias | Resolves to | Notes |
|---|---|---|
| `gemma4` | `gemma4:e4b` | Default Ollama model |
| `lfm2.5` | `lfm2.5:latest` | Liquid Foundation Model |
| `gpt-oss` | `gpt-oss-20b` | Open-source GPT-style |

Any full Ollama model ID (e.g. `llama3.2`, `mistral:latest`) also works — just type it directly into the Model field.

### Performance Tips

- Models with **7B+ parameters** produce significantly better structured output than smaller models.
- `gemma4:e4b` is the recommended default — it handles the JSON-mode structured output well.
- If a model produces garbled or empty output, try a larger variant or switch to a cloud provider.
- Local inference is slower than cloud APIs; Stage 3 runs 3 parallel LLM calls so a capable GPU helps.

## JSON Data Structure

The data files in `data/` directory:
- `profile.json`: Name, title, bio, and social links.
- `experience.json`: Professional work history.
- `education.json`: Academic background.
- `skills.json`: Categorized technical skills.
- `projects.json`: Highlighted projects.
- `contact.json`: Contact information and location.

## Local Command Line (Optional)

Generate LaTeX manually without the UI:
```bash
python scripts/render_resume.py
pdflatex resume.tex
```

## Accessing Your PDF (CI/CD)

Once you push to GitHub, the CI/CD pipeline auto-generates the PDF:
1.  Checking the [**Latest Release**](https://github.com/jangwanAnkit/resume-builder/releases/download/latest/resume.pdf) directly.
2.  Navigating to the **"Releases"** section on the right side of your GitHub repository.
3.  Downloading the `resume.pdf` asset from the **"Latest"** tag.
4. You can check the **"Actions"** tab to see the build progress and logs.
