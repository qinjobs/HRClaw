#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT_DIR/data/pids"
PID_FILE="${SCREENING_SERVER_PID_FILE:-$PID_DIR/phase1_server.pid}"
LABEL_FILE="${SCREENING_SERVER_LABEL_FILE:-$PID_DIR/phase1_server.label}"

remove_launchctl_label() {
  local label="$1"
  if [[ -z "$label" ]] || ! command -v launchctl >/dev/null 2>&1; then
    return 0
  fi
  launchctl remove "$label" >/dev/null 2>&1 || true
}

if [[ -f "$LABEL_FILE" ]]; then
  LABEL="$(cat "$LABEL_FILE" || true)"
  if [[ -n "$LABEL" ]]; then
    echo "[phase1] removing launchctl job label=$LABEL"
    remove_launchctl_label "$LABEL"
  fi
  rm -f "$LABEL_FILE"
fi

if [[ ! -f "$PID_FILE" ]]; then
  echo "[phase1] no pid file found: $PID_FILE"
  exit 0
fi

PID="$(cat "$PID_FILE" || true)"
if [[ -z "$PID" ]]; then
  echo "[phase1] empty pid file, removing"
  rm -f "$PID_FILE"
  exit 0
fi

if ! kill -0 "$PID" >/dev/null 2>&1; then
  echo "[phase1] process $PID is not running, removing stale pid file"
  rm -f "$PID_FILE"
  exit 0
fi

echo "[phase1] stopping server pid=$PID"
kill "$PID"

for _ in $(seq 1 10); do
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    rm -f "$PID_FILE"
    echo "[phase1] server stopped"
    exit 0
  fi
  sleep 1
done

echo "[phase1] process did not exit gracefully, forcing stop"
kill -9 "$PID" >/dev/null 2>&1 || true
rm -f "$PID_FILE"
echo "[phase1] server stopped"
