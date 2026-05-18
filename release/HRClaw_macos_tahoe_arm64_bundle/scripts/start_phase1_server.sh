#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${SCREENING_SERVER_HOST:-127.0.0.1}"
PORT="${SCREENING_SERVER_PORT:-8080}"
PUBLIC_BASE_URL="${SCREENING_PUBLIC_BASE_URL:-http://127.0.0.1:${PORT}}"
LOG_DIR="$ROOT_DIR/data/logs"
PID_DIR="$ROOT_DIR/data/pids"
PID_FILE="${SCREENING_SERVER_PID_FILE:-$PID_DIR/phase1_server.pid}"
LOG_FILE="${SCREENING_SERVER_LOG_FILE:-$LOG_DIR/phase1_server.log}"
LABEL_FILE="${SCREENING_SERVER_LABEL_FILE:-$PID_DIR/phase1_server.label}"
SERVER_LABEL="${SCREENING_SERVER_LABEL:-com.hrclaw.phase1.${PORT}}"
LOG_FILE_EXPLICIT=0
if [[ -n "${SCREENING_SERVER_LOG_FILE:-}" ]]; then
  LOG_FILE_EXPLICIT=1
fi

mkdir -p "$LOG_DIR" "$PID_DIR" "$(dirname "$PID_FILE")" "$(dirname "$LOG_FILE")" "$(dirname "$LABEL_FILE")"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

USE_LAUNCHCTL=0
if [[ "$(uname -s)" == "Darwin" ]] && command -v launchctl >/dev/null 2>&1; then
  USE_LAUNCHCTL=1
fi

ACTUAL_LOG_FILE="$LOG_FILE"
if [[ "$USE_LAUNCHCTL" == "1" && "$LOG_FILE_EXPLICIT" != "1" ]]; then
  ACTUAL_LOG_FILE="${SCREENING_SERVER_LAUNCHCTL_LOG_FILE:-$ROOT_DIR/snapshots/tmp/launchctl/phase1_server_${PORT}.log}"
fi

prepare_log_file() {
  mkdir -p "$(dirname "$ACTUAL_LOG_FILE")"
  if [[ "$USE_LAUNCHCTL" == "1" ]]; then
    chmod 700 "$(dirname "$ACTUAL_LOG_FILE")" 2>/dev/null || true
    rm -f "$ACTUAL_LOG_FILE"
  fi
  if [[ "$ACTUAL_LOG_FILE" != "$LOG_FILE" ]]; then
    rm -f "$LOG_FILE"
    ln -s "$ACTUAL_LOG_FILE" "$LOG_FILE"
  fi
}

cleanup_stale_runtime() {
  local existing_label
  existing_label=""
  if [[ -f "$LABEL_FILE" ]]; then
    existing_label="$(cat "$LABEL_FILE" || true)"
  fi
  if [[ "$USE_LAUNCHCTL" == "1" ]]; then
    if [[ -n "$existing_label" ]]; then
      launchctl remove "$existing_label" >/dev/null 2>&1 || true
    fi
    if [[ "$SERVER_LABEL" != "$existing_label" ]]; then
      launchctl remove "$SERVER_LABEL" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "$PID_FILE" "$LABEL_FILE"
}

listener_pid() {
  lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

launchctl_job_exists() {
  launchctl list 2>/dev/null | awk -v label="$1" '$3 == label {found = 1} END {exit found ? 0 : 1}'
}

if curl -fsS "http://$HOST:$PORT/health" >/dev/null 2>&1; then
  ACTIVE_PID="$(listener_pid)"
  if [[ -n "$ACTIVE_PID" ]]; then
    echo "$ACTIVE_PID" >"$PID_FILE"
  fi
  if [[ "$USE_LAUNCHCTL" == "1" ]]; then
    echo "$SERVER_LABEL" >"$LABEL_FILE"
  fi
  echo "[phase1] server already running: pid=${ACTIVE_PID:-unknown}"
  echo "[phase1] access url: $PUBLIC_BASE_URL"
  exit 0
fi

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE" || true)"
  if [[ -n "$EXISTING_PID" ]] && kill -0 "$EXISTING_PID" >/dev/null 2>&1; then
    cleanup_stale_runtime
  else
    rm -f "$PID_FILE"
  fi
fi

echo "[phase1] starting server bind: http://$HOST:$PORT"
SERVER_CODE="from src.screening.server import run; run(host='$HOST', port=$PORT)"
cleanup_stale_runtime
prepare_log_file

if [[ "$USE_LAUNCHCTL" == "1" ]]; then
  SERVER_COMMAND="cd '$ROOT_DIR'; exec '$PYTHON_BIN' -u -c \"$SERVER_CODE\" >> '$ACTUAL_LOG_FILE' 2>&1"
  launchctl submit -l "$SERVER_LABEL" -p /bin/bash -- /bin/bash -lc "$SERVER_COMMAND"
  echo "$SERVER_LABEL" >"$LABEL_FILE"
  PID=""
else
  nohup env PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON_BIN" -u -c "$SERVER_CODE" >>"$ACTUAL_LOG_FILE" 2>&1 < /dev/null &
  PID=$!
  disown "$PID" 2>/dev/null || true
fi

for _ in $(seq 1 20); do
  if curl -fsS "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    ACTIVE_PID="$(listener_pid)"
    if [[ -n "$ACTIVE_PID" ]]; then
      echo "$ACTIVE_PID" >"$PID_FILE"
    fi
    echo "[phase1] server started: pid=${ACTIVE_PID:-${PID:-unknown}}"
    echo "[phase1] access url: $PUBLIC_BASE_URL"
    echo "[phase1] log file: $LOG_FILE"
    if [[ "$ACTUAL_LOG_FILE" != "$LOG_FILE" ]]; then
      echo "[phase1] runtime log file: $ACTUAL_LOG_FILE"
    fi
    exit 0
  fi
  if [[ "$USE_LAUNCHCTL" == "1" ]]; then
    if ! launchctl_job_exists "$SERVER_LABEL"; then
      echo "[phase1] server exited unexpectedly"
      tail -n 40 "$LOG_FILE" || true
      cleanup_stale_runtime
      exit 1
    fi
  else
    if ! kill -0 "$PID" >/dev/null 2>&1; then
      echo "[phase1] server exited unexpectedly"
      tail -n 40 "$LOG_FILE" || true
      cleanup_stale_runtime
      exit 1
    fi
  fi
  sleep 1
done

echo "[phase1] health check timeout"
tail -n 40 "$LOG_FILE" || true
cleanup_stale_runtime
exit 1
