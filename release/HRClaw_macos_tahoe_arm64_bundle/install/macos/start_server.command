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

CHROME_CDP_PORT="${SCREENING_BROWSER_CDP_PORT:-9222}"
CHROME_PROFILE_DIR="${SCREENING_CHROME_CDP_USER_DATA_DIR:-$HOME/.hrclaw-chrome-cdp-$CHROME_CDP_PORT}"

launch_hrclaw_chrome() {
  mkdir -p "$CHROME_PROFILE_DIR"
  if curl -fsS "http://127.0.0.1:${CHROME_CDP_PORT}/json/version" >/dev/null 2>&1; then
    echo "[phase1] Chrome CDP already available on :$CHROME_CDP_PORT"
    return 0
  fi
  echo "[phase1] launching Google Chrome with CDP port $CHROME_CDP_PORT"
  open -na "Google Chrome" --args \
    --remote-debugging-port="$CHROME_CDP_PORT" \
    --user-data-dir="$CHROME_PROFILE_DIR"
  for _ in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:${CHROME_CDP_PORT}/json/version" >/dev/null 2>&1; then
      echo "[phase1] Chrome CDP ready: http://127.0.0.1:${CHROME_CDP_PORT}"
      return 0
    fi
    sleep 1
  done
  echo "[phase1] warning: Chrome opened but CDP port $CHROME_CDP_PORT is not ready yet"
}

launch_hrclaw_chrome

exec bash "$ROOT_DIR/scripts/start_phase1_server.sh"
