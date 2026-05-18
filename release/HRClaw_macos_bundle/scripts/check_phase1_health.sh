#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${SCREENING_SERVER_HOST:-127.0.0.1}"
PORT="${SCREENING_SERVER_PORT:-8080}"
BASE_URL="${SCREENING_HEALTHCHECK_BASE_URL:-http://127.0.0.1:${PORT}}"
PUBLIC_BASE_URL="${SCREENING_PUBLIC_BASE_URL:-$BASE_URL}"
PLUGIN_DIR="$ROOT_DIR/chrome_extensions/boss_resume_score"

echo "[phase1] checking server health: $BASE_URL/health"
HEALTH_PAYLOAD="$(curl -fsS "$BASE_URL/health")"
echo "[phase1] health response: $HEALTH_PAYLOAD"

echo "[phase1] checking login page"
curl -fsS "$BASE_URL/login" >/dev/null
echo "[phase1] login page OK"

echo "[phase1] checking plugin files"
test -f "$PLUGIN_DIR/manifest.json"
test -f "$PLUGIN_DIR/sidepanel.js"
test -f "$PLUGIN_DIR/service-worker.js"
echo "[phase1] plugin files OK"

echo "[phase1] checking database path"
test -f "$ROOT_DIR/data/screening.db"
echo "[phase1] database OK"

echo "[phase1] public access url: $PUBLIC_BASE_URL"
echo "[phase1] all checks passed"
