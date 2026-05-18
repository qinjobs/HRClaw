#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_DIR="$ROOT_DIR/release"
BUNDLE_NAME="${BUNDLE_NAME:-HRClaw_macos_tahoe_arm64_bundle}"
BUNDLE_DIR="$RELEASE_DIR/$BUNDLE_NAME"
DMG_NAME="${DMG_NAME:-HRClaw_macos_tahoe_arm64_installer.dmg}"
DMG_PATH="$RELEASE_DIR/$DMG_NAME"
VOL_NAME="${VOL_NAME:-HRClaw macOS Installer}"
REFRESH_BUNDLE="${REFRESH_BUNDLE:-1}"

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "[dmg] missing required command: $name" >&2
    exit 1
  fi
}

require_dir() {
  local path="$1"
  if [[ ! -d "$path" ]]; then
    echo "[dmg] missing required directory: $path" >&2
    exit 1
  fi
}

copy_tree() {
  local src="$1"
  local dst="$2"
  rsync -a \
    --exclude ".DS_Store" \
    --exclude "__MACOSX" \
    --exclude "._*" \
    "$src" "$dst"
}

require_command hdiutil
require_command rsync
mkdir -p "$RELEASE_DIR"

if [[ "$REFRESH_BUNDLE" == "1" ]]; then
  echo "[dmg] refreshing base bundle"
  bash "$ROOT_DIR/scripts/build_macos_tahoe_bundle.sh"
fi

require_dir "$BUNDLE_DIR"

STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hrclaw-dmg-stage.XXXXXX")"
cleanup() {
  rm -rf "$STAGE_DIR"
}
trap cleanup EXIT

mkdir -p "$STAGE_DIR/$BUNDLE_NAME"
copy_tree "$BUNDLE_DIR/" "$STAGE_DIR/$BUNDLE_NAME/"

rm -f "$DMG_PATH"
echo "[dmg] creating $DMG_PATH"
hdiutil create \
  -volname "$VOL_NAME" \
  -srcfolder "$STAGE_DIR" \
  -ov \
  -format UDZO \
  -imagekey zlib-level=9 \
  "$DMG_PATH" >/dev/null

echo "[dmg] done"
echo "[dmg] bundle: $BUNDLE_DIR"
echo "[dmg] dmg: $DMG_PATH"
du -sh "$DMG_PATH"
