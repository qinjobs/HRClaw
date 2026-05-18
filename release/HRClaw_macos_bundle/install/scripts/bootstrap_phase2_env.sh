#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_DIR="$ROOT_DIR/install"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REQ_PHASE1="$INSTALL_DIR/packages/python/requirements-phase1.txt"
REQ_OCR="$INSTALL_DIR/packages/python/requirements-phase2-ocr.txt"
REQ_SEARCH="$INSTALL_DIR/packages/python/requirements-phase2-search-optional.txt"
WHEEL_DIR="$INSTALL_DIR/packages/python/wheels"
INSTALL_SEARCH_DEPS="${INSTALL_SEARCH_DEPS:-0}"

echo "[install] project root: $ROOT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e "$ROOT_DIR"
python -m pip install -r "$REQ_PHASE1"

if ! python - <<'PY' >/dev/null 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("paddle") else 1)
PY
then
  LOCAL_WHEEL="$(find "$WHEEL_DIR" -maxdepth 1 -name 'paddlepaddle-*.whl' | head -n 1 || true)"
  if [[ -n "$LOCAL_WHEEL" ]]; then
    echo "[install] installing local PaddlePaddle wheel: $LOCAL_WHEEL"
    python -m pip install "$LOCAL_WHEEL"
  else
    echo "[install] warning: PaddlePaddle not found and no local wheel was packaged."
    echo "[install] install a matching PaddlePaddle build for your OS/CPU/GPU before enabling OCR."
  fi
fi

if [[ -f "$REQ_OCR" ]]; then
  python -m pip install -r "$REQ_OCR"
fi

if [[ "$INSTALL_SEARCH_DEPS" == "1" ]] && [[ -f "$REQ_SEARCH" ]]; then
  python -m pip install -r "$REQ_SEARCH"
fi

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

echo "[install] phase2 bootstrap completed"
echo "[install] notes:"
echo "  - OCR requires PaddlePaddle + PaddleOCR."
echo "  - install enhanced search deps with: INSTALL_SEARCH_DEPS=1 bash install/scripts/bootstrap_phase2_env.sh"
