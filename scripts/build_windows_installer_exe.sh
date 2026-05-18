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
SEVENZIP_COMPRESSION_LEVEL="${SEVENZIP_COMPRESSION_LEVEL:-1}"
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
  local candidate="$sdk_dir/bin/7zSD.sfx"
  if [[ -f "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  candidate="$(find "$sdk_dir" -type f -iname '7zsd.sfx' | head -n 1)"
  if [[ -n "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  echo "[exe] unable to locate the preferred Windows SFX module 7zSD.sfx inside $sdk_dir" >&2
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
echo "[exe] using SFX module: $(basename "$SFX_MODULE")"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hrclaw-exe-stage.XXXXXX")"
ARCHIVE_PATH="$WORK_DIR/${BUNDLE_NAME}.7z"
cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

STAGE_ROOT="$WORK_DIR/stage"
mkdir -p "$STAGE_ROOT"
copy_tree "$BUNDLE_DIR/" "$STAGE_ROOT/$BUNDLE_NAME/"

cat > "$STAGE_ROOT/$BUNDLE_NAME/SFX_LAUNCHER.ps1" <<'LAUNCHER_PS1'
param(
  [string]$InstallDir = $env:HRCLAW_INSTALL_DIR
)

$ErrorActionPreference = "Stop"
$defaultDir = Join-Path $env:USERPROFILE "HRClaw_windows_offline_bundle"
$sourceDir = $PSScriptRoot.TrimEnd("\")

if (-not $InstallDir) {
  Add-Type -AssemblyName System.Windows.Forms
  $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
  $dialog.Description = "Choose the HRClaw installation folder"
  $dialog.SelectedPath = $defaultDir
  $dialog.ShowNewFolderButton = $true

  $result = $dialog.ShowDialog()
  if ($result -ne [System.Windows.Forms.DialogResult]::OK -or [string]::IsNullOrWhiteSpace($dialog.SelectedPath)) {
    Write-Host "[installer] installation cancelled"
    exit 2
  }

  $InstallDir = $dialog.SelectedPath
}

$targetDir = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd("\")
Write-Host "[installer] Using installation folder: $targetDir"

if ($targetDir -ne $sourceDir) {
  New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
  Copy-Item -Path (Join-Path $sourceDir "*") -Destination $targetDir -Recurse -Force
}

$installBat = Join-Path $targetDir "INSTALL.BAT"
if (-not (Test-Path $installBat)) {
  throw "INSTALL.BAT not found in target folder: $targetDir"
}

$proc = Start-Process -FilePath $installBat -WorkingDirectory $targetDir -Wait -PassThru
exit $proc.ExitCode
LAUNCHER_PS1

cat > "$STAGE_ROOT/$BUNDLE_NAME/SFX_LAUNCHER.cmd" <<'LAUNCHER'
@echo off
setlocal
set "TARGET_DIR="
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0SFX_LAUNCHER.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
LAUNCHER

cat > "$WORK_DIR/config.txt" <<CFG
;!@Install@!UTF-8!
Title="HRClaw Windows Offline Installer"
BeginPrompt="Extract HRClaw and choose an installation folder?"
RunProgram="${BUNDLE_NAME}\\SFX_LAUNCHER.cmd"
;!@InstallEnd@!
CFG

rm -f "$ARCHIVE_PATH" "$EXE_PATH"
(
  cd "$STAGE_ROOT"
  "$SEVENZIP_BIN" a -t7z "-mx=$SEVENZIP_COMPRESSION_LEVEL" "$ARCHIVE_PATH" "$BUNDLE_NAME" >/dev/null
)

cat "$SFX_MODULE" "$WORK_DIR/config.txt" "$ARCHIVE_PATH" > "$EXE_PATH"

echo "[exe] done"
echo "[exe] bundle: $BUNDLE_DIR"
echo "[exe] exe: $EXE_PATH"
du -sh "$EXE_PATH"
