# Automated Resume Builder

Manage your professional profile via JSON and get a high-quality LaTeX resume PDF automatically. No local LaTeX installation or syntax knowledge required—GitHub Actions handles the heavy lifting.

[**📄 View Sample Resume**](https://github.com/jangwanAnkit/resume-builder/releases/download/latest/resume.pdf)

## Features

- **Local Web UI**: A minimalist, built-in Customizer UI lets you edit JSON data effortlessly and preview the PDF in real-time.
- **AI-Tailored Resumes**: Fully interoperable with AI agents. Use the [`resume-builder-tailor`](https://github.com/jangwanAnkit/skills/tree/main/resume-builder-tailor) AI skill to completely rewrite your experience data to target specific job descriptions.
- **JSON-based Source of Truth**: Manage all your data (profile, experience, education, skills, projects) in structured JSON files.
- **LaTeX Professionalism**: Utilizes a professional LaTeX template with Jinja2 rendering for a premium look.
- **Automated Workflow**: GitHub Actions automatically compiles your LaTeX source into a PDF on every push to `main`.

## Setup
To use the Local Web UI and compile PDFs on your machine:

1.  **Use as Template / Fork**: Click the **"Use this template"** button to create your own copy.
2.  **Install Dependencies** (for local UI Backend):
    ```bash
    pip install -r requirements.txt
    ```
3.  **Install TeX Live** (to compile LaTeX locally):
    ```bash
    sudo apt install texlive-latex-base texlive-fonts-extra texlive-latex-extra
    ```

## Usage

### 1. Update Data (Recommended: Local Web UI)
Instead of editing JSON manually, you can use the built-in **Resume Customizer UI** to edit your data and preview the generated resume in real-time. The UI features a clean, minimal black-and-white design.

![Resume Customizer UI](docs/pdf_preview_final.png)

1. Install backend dependencies (FastAPI, Uvicorn, Jinja2):
   ```bash
   uv pip install -r requirements.txt
   ```
2. Make sure you have `pdflatex` installed (e.g., `sudo apt install texlive-latex-base texlive-fonts-extra texlive-latex-extra`).
3. Start the customizer server:
   ```bash
   uv run python customizer/server.py
   ```
4. Open [http://localhost:8000](http://localhost:8000) in your browser.
5. Use the UI to edit your profile, experience, education, and projects.
6. Click **Generate** to preview the PDF inline, and **Save to Backend** to write changes back to the JSON files in `data/`.

### 2. Manual JSON Editing
If you prefer, you can manually edit the JSON files in the `data/` directory. The structure is intuitive and keeps your data clean:
- `profile.json`: Name, title, bio, and social links.
- `experience.json`: Professional work history.
- `education.json`: Academic background.
- `skills.json`: Categorized technical skills.
- `projects.json`: Highlighted projects.
- `contact.json`: Contact information and location.

### 3. Generate LaTeX (Local Command Line)
To preview the generated LaTeX code manually in the terminal:
```bash
python scripts/render_resume.py
pdflatex resume.tex
```

## Accessing your PDF
Once you push your code to GitHub, the **CI/CD pipeline** kicks in. You can access your generated PDF by:
1.  Checking the [**Latest Release**](https://github.com/jangwanAnkit/resume-builder/releases/download/latest/resume.pdf) directly.
2.  Navigating to the **"Releases"** section on the right side of your GitHub repository.
3.  Downloading the `resume.pdf` asset from the **"Latest"** tag.
4. You can check the **"Actions"** tab to see the build progress and logs.
