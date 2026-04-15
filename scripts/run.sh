#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: venv not found. Run $ROOT_DIR/scripts/install.sh first."
  exit 1
fi

WORKSPACE="${1:-.}"
shift || true

exec "$PYTHON_BIN" "$ROOT_DIR/heartbeat.py" --workspace "$WORKSPACE" "$@"
