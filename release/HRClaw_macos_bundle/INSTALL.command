#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
while [[ "$ROOT_DIR" != "/" ]]; do
  if [[ -d "$ROOT_DIR/install/packages" ]] && [[ -d "$ROOT_DIR/scripts" ]] && [[ -d "$ROOT_DIR/src" ]]; then
    break
  fi
  ROOT_DIR="$(cd "$ROOT_DIR/.." && pwd)"
done

if [[ "$ROOT_DIR" == "/" ]]; then
  echo "[install] unable to locate HRClaw project root" >&2
  exit 1
fi

cd "$ROOT_DIR"
echo "[install] project root: $ROOT_DIR"

ENV_EXAMPLE="$ROOT_DIR/install/packages/macos/.env.local.example"
if [[ ! -f "$ROOT_DIR/.env.local" ]] && [[ -f "$ENV_EXAMPLE" ]]; then
  cp "$ENV_EXAMPLE" "$ROOT_DIR/.env.local"
  echo "[install] created default .env.local"
fi

bash "$ROOT_DIR/install/scripts/bootstrap_phase1_env.sh"
bash "$ROOT_DIR/install/scripts/restore_frontend_dist.sh"
bash "$ROOT_DIR/scripts/start_phase1_server.sh"

BASE_URL="${SCREENING_PUBLIC_BASE_URL:-http://127.0.0.1:8080}"
echo "[install] installation completed"
echo "[install] login: $BASE_URL/login"
echo "[install] jd scorecard: $BASE_URL/hr/phase2"
echo "[install] resume imports: $BASE_URL/hr/resume-imports"

if command -v open >/dev/null 2>&1; then
  open "$BASE_URL/login" >/dev/null 2>&1 || true
fi
