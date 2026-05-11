#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_DIR="$ROOT_DIR/release"
BUNDLE_NAME="${BUNDLE_NAME:-HRClaw_windows_offline_bundle}"
BUNDLE_DIR="$RELEASE_DIR/$BUNDLE_NAME"
ZIP_PATH="$RELEASE_DIR/${BUNDLE_NAME}.zip"

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "[bundle] missing required file: $path" >&2
    exit 1
  fi
}

require_glob() {
  local pattern="$1"
  if ! compgen -G "$pattern" >/dev/null; then
    echo "[bundle] missing required file pattern: $pattern" >&2
    exit 1
  fi
}

require_wheel() {
  local pattern="$1"
  local wheelhouse="$ROOT_DIR/install/packages/windows/wheelhouse"
  if ! compgen -G "$wheelhouse/$pattern" >/dev/null; then
    echo "[bundle] missing required wheel: $wheelhouse/$pattern" >&2
    exit 1
  fi
}

echo "[bundle] project root: $ROOT_DIR"
mkdir -p "$RELEASE_DIR"

require_file "$ROOT_DIR/pyproject.toml"
require_file "$ROOT_DIR/install/packages/windows/python-3.12.9-amd64.exe"
require_file "$ROOT_DIR/install/packages/windows/chrome-win64.zip"
require_file "$ROOT_DIR/install/packages/windows/admin_frontend-dist.zip"
require_file "$ROOT_DIR/install/packages/windows/.env.local.example"
require_file "$ROOT_DIR/install/packages/windows/uv/uv-x86_64-pc-windows-msvc.zip"
require_file "$ROOT_DIR/docs/HRClaw_Windows客户安装手册.md"
require_glob "$ROOT_DIR/install/packages/windows/kimi-cli/kimi_cli-*.whl"
require_glob "$ROOT_DIR/install/packages/windows/kimi-cli/pywin32_ctypes-*.whl"
require_glob "$ROOT_DIR/install/packages/windows/kimi-cli/ripgrepy-*.whl"
require_glob "$ROOT_DIR/install/packages/windows/kimi-cli/colorama-*.whl"
require_glob "$ROOT_DIR/install/packages/windows/kimi-cli/win32_setctime-*.whl"
require_glob "$ROOT_DIR/install/packages/windows/kimi-cli/pywin32-*.whl"
require_glob "$ROOT_DIR/install/packages/windows/kimi-cli/tzdata-*.whl"

require_wheel "openai-*.whl"
require_wheel "playwright-*.whl"
require_wheel "qdrant_client-*.whl"
require_wheel "requests-*.whl"
require_wheel "certifi-*.whl"
require_wheel "urllib3-*.whl"
require_wheel "idna-*.whl"
require_wheel "charset_normalizer-*.whl"
require_wheel "pypdf-*.whl"
require_wheel "readability_lxml-*.whl"
require_wheel "html2text-*.whl"
require_wheel "lxml-*.whl"
require_wheel "tzdata-*.whl"
require_wheel "pytz-*.whl"

echo "[bundle] preparing staging directory: $BUNDLE_DIR"
rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

copy_tree() {
  local src="$1"
  local dst="$2"
  rsync -a \
    --exclude ".DS_Store" \
    --exclude "__MACOSX" \
    --exclude "._*" \
    --exclude "__pycache__" \
    --exclude "*.pyc" \
    "$src" "$dst"
}

copy_tree "$ROOT_DIR/src" "$BUNDLE_DIR/"
copy_tree "$ROOT_DIR/admin_frontend" "$BUNDLE_DIR/"
copy_tree "$ROOT_DIR/chrome_extensions" "$BUNDLE_DIR/"
copy_tree "$ROOT_DIR/install/packages" "$BUNDLE_DIR/"

cp "$ROOT_DIR/pyproject.toml" "$BUNDLE_DIR/"
cp "$ROOT_DIR/LICENSE" "$BUNDLE_DIR/" || true
cp "$ROOT_DIR/README.md" "$BUNDLE_DIR/" || true
cp "$ROOT_DIR/README.zh-CN.md" "$BUNDLE_DIR/" || true
cp "$ROOT_DIR/docs/HRClaw_Windows客户安装手册.md" "$BUNDLE_DIR/" || true
cp "$ROOT_DIR/docs/HRClaw_个人电脑安装配置建议.md" "$BUNDLE_DIR/" || true

cp "$ROOT_DIR/install/windows/common.ps1" "$BUNDLE_DIR/common.ps1"
cp "$ROOT_DIR/install/windows/install.ps1" "$BUNDLE_DIR/install.ps1"
cp "$ROOT_DIR/install/windows/start_server.ps1" "$BUNDLE_DIR/start_server.ps1"
cp "$ROOT_DIR/install/windows/stop_server.ps1" "$BUNDLE_DIR/stop_server.ps1"
cp "$ROOT_DIR/install/windows/check_health.ps1" "$BUNDLE_DIR/check_health.ps1"
cp "$ROOT_DIR/install/windows/restore_frontend_dist.ps1" "$BUNDLE_DIR/restore_frontend_dist.ps1"
cp "$ROOT_DIR/install/windows/install_uv.ps1" "$BUNDLE_DIR/install_uv.ps1"
cp "$ROOT_DIR/install/windows/install_kimi_cli.ps1" "$BUNDLE_DIR/install_kimi_cli.ps1"

cat > "$BUNDLE_DIR/INSTALL.BAT" <<'EOF'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
endlocal
EOF

cat > "$BUNDLE_DIR/START_SERVER.BAT" <<'EOF'
@echo off
setlocal
if "%SCREENING_BROWSER_CDP_PORT%"=="" set "SCREENING_BROWSER_CDP_PORT=9222"
if "%SCREENING_CHROME_CDP_USER_DATA_DIR%"=="" set "SCREENING_CHROME_CDP_USER_DATA_DIR=%USERPROFILE%\.hrclaw-chrome-cdp-%SCREENING_BROWSER_CDP_PORT%"

set "BUNDLED_CHROME=%~dp0runtime\chrome\chrome-win64\chrome.exe"
set "CHROME_EXE="
if exist "%BUNDLED_CHROME%" set "CHROME_EXE=%BUNDLED_CHROME%"
if "%CHROME_EXE%"=="" if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if "%CHROME_EXE%"=="" if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if "%CHROME_EXE%"=="" if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if not "%CHROME_EXE%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { $r = Invoke-WebRequest -UseBasicParsing -Uri ('http://127.0.0.1:' + $env:SCREENING_BROWSER_CDP_PORT + '/json/version') -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { exit 0 } else { exit 1 } } catch { exit 1 }"
  if errorlevel 1 (
    echo [start] launching Chrome CDP on port %SCREENING_BROWSER_CDP_PORT%
    start "" "%CHROME_EXE%" --remote-debugging-port=%SCREENING_BROWSER_CDP_PORT% --user-data-dir="%SCREENING_CHROME_CDP_USER_DATA_DIR%"
    timeout /t 2 /nobreak >nul
  ) else (
    echo [start] Chrome CDP already available on port %SCREENING_BROWSER_CDP_PORT%
  )
) else (
  echo [start] warning: Chrome executable not found, continue with start_server.ps1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_server.ps1" %*
endlocal
EOF

cat > "$BUNDLE_DIR/STOP_SERVER.BAT" <<'EOF'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_server.ps1" %*
endlocal
EOF

cat > "$BUNDLE_DIR/CHECK_HEALTH.BAT" <<'EOF'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_health.ps1" %*
endlocal
EOF

cat > "$BUNDLE_DIR/INSTALL_UV.BAT" <<'EOF'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_uv.ps1" %*
endlocal
EOF

cat > "$BUNDLE_DIR/INSTALL_KIMI_CLI.BAT" <<'EOF'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_kimi_cli.ps1" %*
endlocal
EOF

cat > "$BUNDLE_DIR/README.md" <<'EOF'
# HRClaw Windows 10 / 11 离线安装包

## 1) 解压
把整个目录解压到本地路径（示例）：

```text
E:\HRClaw_windows_offline_bundle\
```

## 2) 安装（离线）
双击或命令行运行：

```text
INSTALL.BAT
```

默认使用离线附件安装（Python、Chrome、wheelhouse）。

## 3) 启停与检查

- 启动：`START_SERVER.BAT`
- 停止：`STOP_SERVER.BAT`
- 健康检查：`CHECK_HEALTH.BAT`
- 安装 uv：`INSTALL_UV.BAT`
- 安装 kimi-cli：`INSTALL_KIMI_CLI.BAT`

## 4) 默认访问地址

- 登录页：`http://127.0.0.1:8080/login`
- JD评分卡：`http://127.0.0.1:8080/hr/phase2`
- 简历导入：`http://127.0.0.1:8080/hr/resume-imports`

## 5) 可选联网兜底
如果你想让安装脚本在缺包时允许联网兜底：

```text
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -AllowNetworkFallback
```

## 6) 随包文档

- `HRClaw_Windows客户安装手册.md`
- `HRClaw_个人电脑安装配置建议.md`
EOF

chmod +x "$BUNDLE_DIR"/*.bat 2>/dev/null || true

find "$BUNDLE_DIR" -type d -name "__MACOSX" -prune -exec rm -rf {} + >/dev/null 2>&1 || true
find "$BUNDLE_DIR" -type f -name "._*" -delete >/dev/null 2>&1 || true

echo "[bundle] creating zip: $ZIP_PATH"
rm -f "$ZIP_PATH"
(
  cd "$RELEASE_DIR"
  zip -qr -X "$(basename "$ZIP_PATH")" "$(basename "$BUNDLE_DIR")" -x "*/__MACOSX/*" -x "__MACOSX/*" -x "*/._*" -x "._*"
)

echo "[bundle] done"
echo "[bundle] folder: $BUNDLE_DIR"
echo "[bundle] zip: $ZIP_PATH"
du -sh "$BUNDLE_DIR" "$ZIP_PATH"
