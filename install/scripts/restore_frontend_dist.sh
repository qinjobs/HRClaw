#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARCHIVE="$ROOT_DIR/install/packages/frontend/admin_frontend-dist.tgz"
TARGET_DIR="$ROOT_DIR/admin_frontend"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "[install] missing frontend archive: $ARCHIVE" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
tar -xzf "$ARCHIVE" -C "$TARGET_DIR"
echo "[install] frontend dist restored to $TARGET_DIR/dist"
