#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[phase1] project root: $ROOT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[phase1] creating virtualenv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "[phase1] using existing virtualenv: $VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e "$ROOT_DIR" playwright openai qdrant-client
python -m playwright install chromium

mkdir -p \
  "$ROOT_DIR/data/auth" \
  "$ROOT_DIR/data/logs" \
  "$ROOT_DIR/data/pids" \
  "$ROOT_DIR/data/qdrant_search" \
  "$ROOT_DIR/data/resumes" \
  "$ROOT_DIR/data/runs" \
  "$ROOT_DIR/data/screenshots" \
  "$ROOT_DIR/snapshots/tmp"

echo "[phase1] bootstrap completed"
echo "[phase1] next steps:"
echo "  1. cp .env.local.example .env.local"
echo "  2. PYTHONPATH=. $VENV_DIR/bin/python scripts/save_boss_storage_state.py"
echo "  3. bash scripts/start_phase1_server.sh"
