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

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
  echo "[install] warning: this package targets Apple Silicon (M1/M2/M3/M4). current arch: $ARCH"
fi

if command -v sw_vers >/dev/null 2>&1; then
  MACOS_VERSION="$(sw_vers -productVersion)"
  MACOS_MAJOR="${MACOS_VERSION%%.*}"
  if [[ "$MACOS_MAJOR" =~ ^[0-9]+$ ]]; then
    if (( MACOS_MAJOR < 26 )); then
      echo "[install] warning: recommended macOS Tahoe 26+; current version: $MACOS_VERSION"
    else
      echo "[install] detected macOS $MACOS_VERSION"
    fi
  fi
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "[install] python3 not found. please install Python 3.12+ first." >&2
    exit 1
  fi
fi

PYTHON_VERSION="$("$PYTHON_BIN" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || true)"
if [[ -z "$PYTHON_VERSION" ]]; then
  echo "[install] cannot query python version from: $PYTHON_BIN" >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "[install] Python 3.12+ is required, but got: $PYTHON_VERSION ($PYTHON_BIN)" >&2
  echo "[install] please install Python 3.12+ and rerun, for example:" >&2
  echo "[install]   brew install python@3.12" >&2
  echo "[install]   PYTHON_BIN=\$(which python3.12) ./INSTALL.command" >&2
  exit 1
fi

echo "[install] using python: $PYTHON_BIN ($PYTHON_VERSION)"
export PYTHON_BIN

cd "$ROOT_DIR"
echo "[install] project root: $ROOT_DIR"

ENV_EXAMPLE="$ROOT_DIR/install/packages/macos/.env.local.example"
if [[ ! -f "$ROOT_DIR/.env.local" ]] && [[ -f "$ENV_EXAMPLE" ]]; then
  cp "$ENV_EXAMPLE" "$ROOT_DIR/.env.local"
  echo "[install] created default .env.local"
fi

detect_kimi_cli() {
  local candidates=()
  if command -v kimi >/dev/null 2>&1; then
    candidates+=("$(command -v kimi)")
  fi
  candidates+=(
    "$HOME/.local/bin/kimi"
    "$HOME/.cargo/bin/kimi"
    "$HOME/.npm-global/bin/kimi"
    "/opt/homebrew/bin/kimi"
    "/usr/local/bin/kimi"
  )
  for candidate in "${candidates[@]}"; do
    if [[ -n "$candidate" ]] && [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if [[ -f "$ROOT_DIR/.env.local" ]]; then
  if KIMI_BIN="$(detect_kimi_cli)"; then
    if grep -q '^SCREENING_KIMI_CLI_COMMAND=' "$ROOT_DIR/.env.local"; then
      python3 - <<PY
from pathlib import Path
path = Path(r"$ROOT_DIR/.env.local")
text = path.read_text(encoding="utf-8")
lines = text.splitlines()
updated = []
for line in lines:
    if line.startswith("SCREENING_KIMI_CLI_COMMAND="):
        updated.append(f"SCREENING_KIMI_CLI_COMMAND={r'''$KIMI_BIN'''}")
    else:
        updated.append(line)
path.write_text("\n".join(updated) + ("\n" if text.endswith("\n") or text else "\n"), encoding="utf-8")
PY
    else
      printf '\nSCREENING_KIMI_CLI_COMMAND=%s\n' "$KIMI_BIN" >> "$ROOT_DIR/.env.local"
    fi
    echo "[install] detected kimi-cli: $KIMI_BIN"
  else
    echo "[install] warning: kimi-cli not found in common paths; scoring will fallback until SCREENING_KIMI_CLI_COMMAND is configured"
  fi
fi

bash "$ROOT_DIR/install/scripts/bootstrap_phase1_env.sh"
bash "$ROOT_DIR/install/scripts/restore_frontend_dist.sh"

BASE_URL="${SCREENING_PUBLIC_BASE_URL:-http://127.0.0.1:8080}"
echo "[install] installation completed"
echo "[install] service is not started automatically by default"
echo "[install] run START_SERVER.command manually when you are ready"
echo "[install] then open: $BASE_URL/login"
echo "[install] jd scorecard: $BASE_URL/hr/phase2"
echo "[install] resume imports: $BASE_URL/hr/resume-imports"
