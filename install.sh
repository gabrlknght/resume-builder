#!/bin/bash
# install.sh — First-time setup for the Resume Builder + AI Tailoring pipeline.
#
# What this script does:
#   1. Installs Python dependencies (fastapi, uvicorn, openai, instructor, etc.)
#   2. Optionally installs TeX Live for local PDF compilation
#   3. Optionally installs Ollama for 100% offline / local LLM tailoring
#   4. Optionally pulls a recommended Ollama model
#   5. Prints a summary of next steps
#
# Usage:
#   bash install.sh
#
# Flags (non-interactive):
#   --no-tex      Skip TeX Live installation
#   --no-ollama   Skip Ollama installation
#   --model NAME  Ollama model to pull (default: gemma4:e4b)
#   --yes         Auto-accept all prompts (non-interactive mode)

set -e

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
SKIP_TEX=false
SKIP_OLLAMA=false
OLLAMA_MODEL="gemma4:e4b"
AUTO_YES=false

show_help() {
    cat <<'HELP'
Usage: bash install.sh [OPTIONS]

  First-time setup for the Resume Builder + AI Tailoring pipeline.

Options:
  --no-tex      Skip TeX Live installation
  --no-ollama   Skip Ollama installation
  --model NAME  Ollama model to pull (default: gemma4:e4b)
                 Examples: llama3.2, lfm2.5:latest, mistral:latest, qwen3.5:e4b
  --yes, -y     Auto-accept all prompts (non-interactive mode)
  --help, -h    Show this help message

Examples:
  # Install everything (interactive prompts)
  bash install.sh

  # Skip TeX Live, install Ollama with llama3.2, auto-accept
  bash install.sh --no-tex --model llama3.2 --yes

  # Show help
  bash install.sh --help

HELP
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-tex)     SKIP_TEX=true; shift ;;
        --no-ollama)  SKIP_OLLAMA=true; shift ;;
        --yes|-y)     AUTO_YES=true; shift ;;
        --model=*)    OLLAMA_MODEL="${1#--model=}"; shift ;;
        --model)
            if [[ -z "${2:-}" ]]; then
                echo "ERROR: --model requires a value" >&2
                show_help
            fi
            OLLAMA_MODEL="$2"; shift 2 ;;
        --help|-h)    show_help ;;
        *) shift ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
CYAN="\033[36m"
BOLD="\033[1m"
RESET="\033[0m"

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; }
header()  { echo -e "\n${BOLD}=== $* ===${RESET}"; }

ask_yes_no() {
    # ask_yes_no "Question" → returns 0 (yes) or 1 (no)
    local prompt="$1"
    if $AUTO_YES; then
        echo -e "${CYAN}[AUTO]${RESET}  $prompt → yes"
        return 0
    fi
    read -rp "$(echo -e "${CYAN}?${RESET} $prompt [Y/n] ")" answer
    case "${answer,,}" in
        n|no) return 1 ;;
        *)    return 0 ;;
    esac
}

# ---------------------------------------------------------------------------
# 0. Pre-flight checks
# ---------------------------------------------------------------------------
header "Resume Builder — Setup"
echo "This installer sets up everything you need to run the Local Web UI"
echo "and optionally the Local LLM (Ollama) tailoring pipeline."
echo ""

OS="$(uname -s)"
if [[ "$OS" != "Linux" && "$OS" != "Darwin" ]]; then
    warn "Detected OS: $OS. This script is designed for Linux/macOS."
    warn "Windows users: run inside WSL2 for best compatibility."
fi

# ---------------------------------------------------------------------------
# 1. Python dependencies
# ---------------------------------------------------------------------------
header "Step 1: Python Dependencies"

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    error "Python not found. Please install Python 3.9+ and re-run this script."
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Found Python $PYTHON_VERSION via '$PYTHON_CMD'"

PIP_INSTALL=""
if command -v uv &>/dev/null; then
    info "Using 'uv' for fast dependency installation."
    PIP_INSTALL="uv pip install"
elif command -v pip3 &>/dev/null; then
    warn "'uv' not found — falling back to pip3. Install uv for faster installs: https://docs.astral.sh/uv/"
    PIP_INSTALL="pip3 install"
elif command -v pip &>/dev/null; then
    warn "'uv' not found — falling back to pip."
    PIP_INSTALL="pip install"
else
    error "No pip or uv found. Install pip: https://pip.pypa.io/en/stable/installation/"
    exit 1
fi

info "Installing Python packages from requirements.txt..."
$PIP_INSTALL -r requirements.txt
success "Python dependencies installed."

# ---------------------------------------------------------------------------
# 2. Node.js build (minified static assets)
# ---------------------------------------------------------------------------
header "Step 2: Node.js Build (Minified Static Assets)"

if command -v npm &>/dev/null; then
    info "Installing Node dev dependencies and building minified assets..."
    npm ci --silent
    npm run build
    success "Static assets minified (app.min.js, style.min.css)."
else
    warn "npm not found — skipping asset minification."
    warn "Install Node.js to enable minified production builds: https://nodejs.org/"
    warn "Then run: npm ci && npm run build"
fi

# ---------------------------------------------------------------------------
# 3. TeX Live (for local PDF compilation)
# ---------------------------------------------------------------------------
header "Step 3: TeX Live (Local PDF Compilation)"

if $SKIP_TEX; then
    info "Skipping TeX Live installation (--no-tex)."
elif command -v pdflatex &>/dev/null; then
    success "pdflatex already installed — skipping TeX Live."
else
    warn "pdflatex not found. Without it, PDF generation in the Web UI will not work."
    echo "  You can still use CI/CD (push to GitHub) to generate PDFs."
    echo ""
    if ask_yes_no "Install TeX Live now? (requires sudo, ~200 MB)"; then
        if [[ "$OS" == "Linux" ]]; then
            if command -v apt-get &>/dev/null; then
                info "Installing via apt-get..."
                sudo apt-get update -qq
                sudo apt-get install -y texlive-latex-base texlive-fonts-extra texlive-latex-extra
                success "TeX Live installed."
            elif command -v dnf &>/dev/null; then
                info "Installing via dnf..."
                sudo dnf install -y texlive-latex texlive-collection-fontsrecommended
                success "TeX Live installed."
            elif command -v pacman &>/dev/null; then
                info "Installing via pacman..."
                sudo pacman -S --noconfirm texlive-core texlive-fontsextra
                success "TeX Live installed."
            else
                warn "Could not detect package manager. Install TeX Live manually:"
                warn "  https://www.tug.org/texlive/"
            fi
        elif [[ "$OS" == "Darwin" ]]; then
            if command -v brew &>/dev/null; then
                info "Installing MacTeX via Homebrew (this may take a while)..."
                brew install --cask mactex-no-gui
                success "MacTeX installed."
            else
                warn "Homebrew not found. Download MacTeX from https://www.tug.org/mactex/"
            fi
        fi
    else
        info "Skipping TeX Live. You can install it later with:"
        info "  sudo apt install texlive-latex-base texlive-fonts-extra texlive-latex-extra"
    fi
fi

# ---------------------------------------------------------------------------
# 4. Ollama (Local LLM — no API key needed)
# ---------------------------------------------------------------------------
header "Step 4: Ollama — Local LLM (Optional)"
echo "Ollama lets you run the AI tailoring pipeline 100% offline."
echo "No API key required. Recommended model: gemma4:e4b (~5 GB)"
echo ""

if $SKIP_OLLAMA; then
    info "Skipping Ollama installation (--no-ollama)."
elif command -v ollama &>/dev/null; then
    success "Ollama already installed ($(ollama --version 2>/dev/null || echo 'version unknown'))."
    OLLAMA_INSTALLED=true
else
    if ask_yes_no "Install Ollama for local LLM support?"; then
        info "Downloading and installing Ollama..."
        if [[ "$OS" == "Linux" || "$OS" == "Darwin" ]]; then
            curl -fsSL https://ollama.com/install.sh | sh
            success "Ollama installed."
            OLLAMA_INSTALLED=true
        else
            warn "Automatic Ollama install is not supported on $OS."
            warn "Download manually from https://ollama.com/download"
            OLLAMA_INSTALLED=false
        fi
    else
        info "Skipping Ollama. You can install it later from https://ollama.com"
        OLLAMA_INSTALLED=false
    fi
fi

# ---------------------------------------------------------------------------
# 5. Pull Ollama model
# ---------------------------------------------------------------------------
if [[ "${OLLAMA_INSTALLED:-false}" == "true" ]]; then
    header "Step 5: Pull Ollama Model"
    echo "Available recommended models:"
    echo "  gemma4:e4b — Default, best quality for resume tailoring (~5 GB)"
    echo "  llama3.2        — Lightweight option (~2 GB)"
    echo "  lfm2.5:latest   — Liquid Foundation Model (~3 GB)"
    echo "  mistral:latest  — Good general purpose (~4 GB)"
    echo "  qwen3.5:e4b — Qwen 3.5 (~5 GB)"
    echo "  gpt-oss:20b     — Open-source GPT-style (~10 GB)"
    echo ""
    echo "Selected model: ${OLLAMA_MODEL}"
    echo "(Override with: bash install.sh --model llama3.2)"
    echo ""

    if ask_yes_no "Pull '${OLLAMA_MODEL}' now? (this may take several minutes)"; then
        # Ensure ollama daemon is running
        if ! pgrep -x ollama &>/dev/null; then
            info "Starting Ollama daemon..."
            ollama serve &>/dev/null &
            sleep 3
        fi
        info "Pulling ${OLLAMA_MODEL}..."
        ollama pull "${OLLAMA_MODEL}"
        success "Model '${OLLAMA_MODEL}' ready."
    else
        info "Skipping model pull. Pull later with: ollama pull ${OLLAMA_MODEL}"
    fi
else
    header "Step 5: Pull Ollama Model"
    info "Ollama not installed — skipping model pull."
fi

# ---------------------------------------------------------------------------
# 6. Optional: API key environment variables
# ---------------------------------------------------------------------------
header "Step 6: Cloud Provider API Keys (Optional)"
echo "If you plan to use cloud providers (OpenAI, Cerebras, Gemini, etc.), you can"
echo "set your API keys as environment variables so you don't paste them in the UI"
echo "every time. Add these to your shell profile (~/.bashrc or ~/.zshrc):"
echo ""
echo "  export OPENAI_API_KEY=\"sk-...\""
echo "  export CEREBRAS_API_KEY=\"...\""
echo "  export GEMINI_API_KEY=\"...\""
echo "  export OPENROUTER_API_KEY=\"...\""
echo ""
echo "The server reads <PROVIDER>_API_KEY automatically on startup."
echo "Ollama (local) requires no API key — just select it in the UI."

# ---------------------------------------------------------------------------
# 7. Done — summary
# ---------------------------------------------------------------------------
header "Setup Complete"

echo ""
echo -e "${GREEN}${BOLD}Everything is ready. Next steps:${RESET}"
echo ""
echo -e "  ${BOLD}1. Start the server:${RESET}"
if command -v uv &>/dev/null; then
    echo "       uv run python customizer/server.py"
else
    echo "       ${PYTHON_CMD} customizer/server.py"
fi
echo ""
echo -e "  ${BOLD}2. Open the UI in your browser:${RESET}"
echo "       http://localhost:7777"
echo ""
echo -e "  ${BOLD}3. (Optional) Change host/port:${RESET}"
if command -v uv &>/dev/null; then
    echo "       uv run uvicorn customizer.server:app --host 0.0.0.0 --port 8080"
else
    echo "       ${PYTHON_CMD} -m uvicorn customizer.server:app --host 0.0.0.0 --port 8080"
fi
echo ""

if [[ "${OLLAMA_INSTALLED:-false}" == "true" ]]; then
    echo -e "  ${BOLD}4. For local LLM tailoring:${RESET}"
    echo "       - Select 'Ollama (Local)' in the AI provider dropdown"
    echo "       - Default endpoint: http://localhost:11434"
    echo "       - No API key needed"
    echo ""
fi

echo -e "  ${BOLD}Need help?${RESET} See README.md or open an issue on GitHub."
echo ""