#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN=""
if command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="python3.12"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="python3.11"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Error: Python 3 not found. Install Python 3.11 or 3.12 and retry."
  exit 1
fi

echo "Using interpreter: $PYTHON_BIN"
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo
echo "Install complete."
echo "Use this runner from any project directory:"
echo "  $ROOT_DIR/scripts/run.sh . --interval 60"
