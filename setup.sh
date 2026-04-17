#!/usr/bin/env bash
# setup.sh — Bootstrap ytb from scratch
# Works on Linux / macOS / WSL
# Usage: bash setup.sh

set -euo pipefail

VENV_DIR=".venv"
PYTHON_MIN="3.8"

# ── helpers ────────────────────────────────────────────────────────────────────
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[34m%s\033[0m\n' "$*"; }
step()  { blue "==> $*"; }

# ── find python3 ───────────────────────────────────────────────────────────────
step "Checking Python version (>= ${PYTHON_MIN} required)"
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>/dev/null || true)
        if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    red "Python >= ${PYTHON_MIN} not found. Install it first:"
    red "  Ubuntu/Debian: sudo apt install python3 python3-venv"
    red "  macOS:         brew install python"
    exit 1
fi
green "  Found: $($PYTHON --version)"

# ── create virtual environment ─────────────────────────────────────────────────
step "Creating virtual environment at ${VENV_DIR}/"
if [[ -d "$VENV_DIR" ]]; then
    green "  Already exists, skipping."
else
    "$PYTHON" -m venv "$VENV_DIR"
    green "  Created."
fi

# ── activate + upgrade pip ─────────────────────────────────────────────────────
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
step "Upgrading pip"
pip install --upgrade pip --quiet
green "  pip $(pip --version | awk '{print $2}')"

# ── install dependencies ───────────────────────────────────────────────────────
step "Installing dependencies from requirements.txt"
pip install -r requirements.txt --quiet
green "  yt-dlp $(pip show yt-dlp | awk '/^Version/{print $2}')"
green "  youtube-transcript-api $(pip show youtube-transcript-api | awk '/^Version/{print $2}')"

# ── make ytb.py executable ─────────────────────────────────────────────────────
step "Making ytb.py executable"
chmod +x ytb.py
green "  Done."

# ── optional: shell alias hint ─────────────────────────────────────────────────
YTB_PATH="$(pwd)/ytb.py"
ACTIVATE_PATH="$(pwd)/${VENV_DIR}/bin/activate"

printf '\n'
green "Setup complete! Run transcripts with:"
printf '\n'
printf '  source %s && python ytb.py --help\n' "$ACTIVATE_PATH"
printf '\n'
printf 'Or add this alias to your ~/.bashrc / ~/.zshrc for a global command:\n'
printf '\n'
printf '  alias ytb="source %s && python %s"\n' "$ACTIVATE_PATH" "$YTB_PATH"
printf '\n'
printf 'Quick examples:\n'
printf '  ytb --channel https://www.youtube.com/@mkbhd\n'
printf '  ytb --channel https://www.youtube.com/@mkbhd --limit 5\n'
printf '  ytb --channel https://www.youtube.com/@mkbhd --from 2024-01-01 --to 2024-06-30\n'
printf '  ytb --urls https://youtu.be/VIDEO_ID\n'
