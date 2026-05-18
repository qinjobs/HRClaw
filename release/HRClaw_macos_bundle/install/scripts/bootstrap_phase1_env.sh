#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_DIR="$ROOT_DIR/install"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REQ_FILE="$INSTALL_DIR/packages/python/requirements-phase1.txt"

echo "[install] project root: $ROOT_DIR"

if [[ ! -f "$REQ_FILE" ]]; then
  echo "[install] missing requirements file: $REQ_FILE" >&2
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[install] creating virtualenv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "[install] using existing virtualenv: $VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e "$ROOT_DIR"
python -m pip install -r "$REQ_FILE"
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

echo "[install] phase1 bootstrap completed"
echo "[install] next steps:"
echo "  1. cp install/packages/config/.env.local.example .env.local"
echo "  2. bash install/scripts/start_server.sh"
echo "  3. bash install/scripts/check_health.sh"
