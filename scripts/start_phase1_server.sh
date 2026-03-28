#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${SCREENING_SERVER_HOST:-127.0.0.1}"
PORT="${SCREENING_SERVER_PORT:-8080}"
PUBLIC_BASE_URL="${SCREENING_PUBLIC_BASE_URL:-http://127.0.0.1:${PORT}}"
LOG_DIR="$ROOT_DIR/data/logs"
PID_DIR="$ROOT_DIR/data/pids"
PID_FILE="$PID_DIR/phase1_server.pid"
LOG_FILE="$LOG_DIR/phase1_server.log"

mkdir -p "$LOG_DIR" "$PID_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE" || true)"
  if [[ -n "$EXISTING_PID" ]] && kill -0 "$EXISTING_PID" >/dev/null 2>&1; then
    echo "[phase1] server already running: pid=$EXISTING_PID"
    echo "[phase1] access url: $PUBLIC_BASE_URL"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

echo "[phase1] starting server bind: http://$HOST:$PORT"
SERVER_CODE="from src.screening.server import run; run(host='$HOST', port=$PORT)"
if command -v setsid >/dev/null 2>&1; then
  PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  setsid "$PYTHON_BIN" -c "$SERVER_CODE" >>"$LOG_FILE" 2>&1 < /dev/null &
else
  PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  nohup "$PYTHON_BIN" -c "$SERVER_CODE" >>"$LOG_FILE" 2>&1 < /dev/null &
fi

PID=$!
echo "$PID" >"$PID_FILE"

for _ in $(seq 1 20); do
  if curl -fsS "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    echo "[phase1] server started: pid=$PID"
    echo "[phase1] access url: $PUBLIC_BASE_URL"
    echo "[phase1] log file: $LOG_FILE"
    exit 0
  fi
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    echo "[phase1] server exited unexpectedly"
    tail -n 40 "$LOG_FILE" || true
    rm -f "$PID_FILE"
    exit 1
  fi
  sleep 1
done

echo "[phase1] health check timeout"
tail -n 40 "$LOG_FILE" || true
exit 1
