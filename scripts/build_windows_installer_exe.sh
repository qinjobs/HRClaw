#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_DIR="$ROOT_DIR/release"
BUNDLE_NAME="${BUNDLE_NAME:-HRClaw_windows_offline_bundle}"
BUNDLE_DIR="$RELEASE_DIR/$BUNDLE_NAME"
EXE_NAME="${EXE_NAME:-HRClaw_windows_offline_installer.exe}"
EXE_PATH="$RELEASE_DIR/$EXE_NAME"
REFRESH_BUNDLE="${REFRESH_BUNDLE:-1}"
SEVENZIP_VERSION="${SEVENZIP_VERSION:-2601}"
TOOLS_DIR="${TOOLS_DIR:-${TMPDIR:-/tmp}/hrclaw-installer-tools-$SEVENZIP_VERSION}"
MAC_ARCHIVE_URL="https://7-zip.org/a/7z${SEVENZIP_VERSION}-mac.tar.xz"
SDK_ARCHIVE_URL="https://7-zip.org/a/lzma${SEVENZIP_VERSION}.7z"

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "[exe] missing required command: $name" >&2
    exit 1
  fi
}

require_dir() {
  local path="$1"
  if [[ ! -d "$path" ]]; then
    echo "[exe] missing required directory: $path" >&2
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

ensure_7zip_tools() {
  local sevenzip_bin="$TOOLS_DIR/7zz"
  local sdk_dir="$TOOLS_DIR/lzma-sdk"

  mkdir -p "$TOOLS_DIR"

  if [[ ! -x "$sevenzip_bin" ]]; then
    echo "[exe] downloading 7-Zip mac binary"
    curl -L "$MAC_ARCHIVE_URL" -o "$TOOLS_DIR/7z-mac.tar.xz"
    tar -xf "$TOOLS_DIR/7z-mac.tar.xz" -C "$TOOLS_DIR"
    chmod +x "$sevenzip_bin"
  fi

  if [[ ! -d "$sdk_dir" ]]; then
    echo "[exe] downloading LZMA SDK package"
    curl -L "$SDK_ARCHIVE_URL" -o "$TOOLS_DIR/lzma-sdk.7z"
    mkdir -p "$sdk_dir"
    "$sevenzip_bin" x -y "$TOOLS_DIR/lzma-sdk.7z" "-o$sdk_dir" >/dev/null
  fi

  if [[ ! -x "$sevenzip_bin" ]]; then
    echo "[exe] 7zz binary not found after extraction" >&2
    exit 1
  fi
}

find_sfx_module() {
  local sdk_dir="$TOOLS_DIR/lzma-sdk"
  local candidate
  for candidate in \
    "$sdk_dir/bin/7zSD.sfx" \
    "$sdk_dir/bin/7zS2.sfx" \
    "$sdk_dir/bin/7zS2con.sfx"
  do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  candidate="$(find "$sdk_dir" -type f \( -iname '7zsd.sfx' -o -iname '7zs2.sfx' -o -iname '7zs2con.sfx' \) | head -n 1)"
  if [[ -n "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  echo "[exe] unable to locate a Windows SFX module inside $sdk_dir" >&2
  exit 1
}

require_command curl
require_command tar
require_command rsync
mkdir -p "$RELEASE_DIR"

if [[ "$REFRESH_BUNDLE" == "1" ]]; then
  echo "[exe] refreshing base bundle"
  bash "$ROOT_DIR/scripts/build_windows_offline_bundle.sh"
fi

require_dir "$BUNDLE_DIR"
ensure_7zip_tools

SEVENZIP_BIN="$TOOLS_DIR/7zz"
SFX_MODULE="$(find_sfx_module)"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hrclaw-exe-stage.XXXXXX")"
ARCHIVE_PATH="$WORK_DIR/${BUNDLE_NAME}.7z"
cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

STAGE_ROOT="$WORK_DIR/stage"
mkdir -p "$STAGE_ROOT"
copy_tree "$BUNDLE_DIR/" "$STAGE_ROOT/$BUNDLE_NAME/"

cat > "$STAGE_ROOT/$BUNDLE_NAME/SFX_LAUNCHER.cmd" <<'LAUNCHER'
@echo off
setlocal
set "SRC_DIR=%~dp0"
if "%SRC_DIR:~-1%"=="\" set "SRC_DIR=%SRC_DIR:~0,-1%"
set "TARGET_DIR=%USERPROFILE%\HRClaw_windows_offline_bundle"

echo [installer] Copying bundle to "%TARGET_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$src=$env:SRC_DIR; $dst=$env:TARGET_DIR; New-Item -ItemType Directory -Force -Path $dst | Out-Null; Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force"
if errorlevel 1 exit /b 1

echo [installer] Launching INSTALL.BAT
call "%TARGET_DIR%\INSTALL.BAT"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
LAUNCHER

cat > "$WORK_DIR/config.txt" <<CFG
;!@Install@!UTF-8!
Title="HRClaw Windows Offline Installer"
BeginPrompt="Extract HRClaw to %USERPROFILE%\\HRClaw_windows_offline_bundle and launch INSTALL.BAT?"
RunProgram="${BUNDLE_NAME}\\SFX_LAUNCHER.cmd"
;!@InstallEnd@!
CFG

rm -f "$ARCHIVE_PATH" "$EXE_PATH"
(
  cd "$STAGE_ROOT"
  "$SEVENZIP_BIN" a -t7z -mx=9 "$ARCHIVE_PATH" "$BUNDLE_NAME" >/dev/null
)

cat "$SFX_MODULE" "$WORK_DIR/config.txt" "$ARCHIVE_PATH" > "$EXE_PATH"

echo "[exe] done"
echo "[exe] bundle: $BUNDLE_DIR"
echo "[exe] exe: $EXE_PATH"
du -sh "$EXE_PATH"
