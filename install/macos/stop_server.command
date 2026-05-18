#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
while [[ "$ROOT_DIR" != "/" ]]; do
  if [[ -d "$ROOT_DIR/scripts" ]] && [[ -d "$ROOT_DIR/src" ]]; then
    break
  fi
  ROOT_DIR="$(cd "$ROOT_DIR/.." && pwd)"
done

if [[ "$ROOT_DIR" == "/" ]]; then
  echo "[phase1] unable to locate HRClaw project root" >&2
  exit 1
fi

exec bash "$ROOT_DIR/scripts/stop_phase1_server.sh"
