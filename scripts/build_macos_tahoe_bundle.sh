#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_DIR="$ROOT_DIR/release"
BUNDLE_NAME="${BUNDLE_NAME:-HRClaw_macos_tahoe_arm64_bundle}"
BUNDLE_DIR="$RELEASE_DIR/$BUNDLE_NAME"
ZIP_PATH="$RELEASE_DIR/${BUNDLE_NAME}.zip"
TAR_PATH="$RELEASE_DIR/${BUNDLE_NAME}.tar.gz"

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "[bundle] missing required file: $path" >&2
    exit 1
  fi
}

echo "[bundle] project root: $ROOT_DIR"
mkdir -p "$RELEASE_DIR"

require_file "$ROOT_DIR/pyproject.toml"
require_file "$ROOT_DIR/install/macos/INSTALL.command"
require_file "$ROOT_DIR/install/macos/start_server.command"
require_file "$ROOT_DIR/install/macos/stop_server.command"
require_file "$ROOT_DIR/install/macos/check_health.command"
require_file "$ROOT_DIR/install/packages/macos/.env.local.example"
require_file "$ROOT_DIR/install/packages/macos/README.md"
require_file "$ROOT_DIR/install/packages/frontend/admin_frontend-dist.tgz"
require_file "$ROOT_DIR/install/packages/python/requirements-phase1.txt"
require_file "$ROOT_DIR/install/packages/python/requirements-phase2-ocr.txt"
require_file "$ROOT_DIR/install/packages/python/wheels/paddlepaddle-3.3.0-cp312-cp312-macosx_11_0_arm64.whl"

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
copy_tree "$ROOT_DIR/scripts" "$BUNDLE_DIR/"
copy_tree "$ROOT_DIR/install" "$BUNDLE_DIR/"
copy_tree "$ROOT_DIR/chrome_extensions" "$BUNDLE_DIR/"

cp "$ROOT_DIR/pyproject.toml" "$BUNDLE_DIR/"
cp "$ROOT_DIR/README.md" "$BUNDLE_DIR/" || true
cp "$ROOT_DIR/README.zh-CN.md" "$BUNDLE_DIR/" || true
cp "$ROOT_DIR/CHANGELOG.md" "$BUNDLE_DIR/" || true
cp "$ROOT_DIR/SECURITY.md" "$BUNDLE_DIR/" || true
cp "$ROOT_DIR/LICENSE" "$BUNDLE_DIR/" || true

cat > "$BUNDLE_DIR/INSTALL.command" <<'EOF'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/install/macos/INSTALL.command" "$@"
EOF

cat > "$BUNDLE_DIR/START_SERVER.command" <<'EOF'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/install/macos/start_server.command" "$@"
EOF

cat > "$BUNDLE_DIR/STOP_SERVER.command" <<'EOF'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/install/macos/stop_server.command" "$@"
EOF

cat > "$BUNDLE_DIR/CHECK_HEALTH.command" <<'EOF'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/install/macos/check_health.command" "$@"
EOF

cat > "$BUNDLE_DIR/README-BUNDLE.md" <<'EOF'
# HRClaw macOS 安装包（Tahoe 26+ / Apple Silicon）

该安装包面向 Apple Silicon（M1 及以上）设备，目标系统为 macOS Tahoe 26 及后续版本。

## 安装

1. 解压整个目录到本地，例如：
   `~/HRClaw_macos_tahoe_arm64_bundle`
2. 双击运行根目录：`INSTALL.command`
3. 安装完成后手工执行：`START_SERVER.command`
4. 再访问：
   `http://127.0.0.1:8080/login`

## 维护入口

- 启动服务：`START_SERVER.command`
- 停止服务：`STOP_SERVER.command`
- 健康检查：`CHECK_HEALTH.command`
EOF

chmod +x "$BUNDLE_DIR/"*.command
chmod +x "$BUNDLE_DIR/install/macos/"*.command
chmod +x "$BUNDLE_DIR/install/scripts/"*.sh
chmod +x "$BUNDLE_DIR/scripts/"*.sh || true

find "$BUNDLE_DIR" -type d -name "__MACOSX" -prune -exec rm -rf {} + >/dev/null 2>&1 || true
find "$BUNDLE_DIR" -type f -name "._*" -delete >/dev/null 2>&1 || true

echo "[bundle] creating zip: $ZIP_PATH"
rm -f "$ZIP_PATH"
(
  cd "$RELEASE_DIR"
  zip -qr -X "$(basename "$ZIP_PATH")" "$(basename "$BUNDLE_DIR")" -x "*/__MACOSX/*" -x "__MACOSX/*" -x "*/._*" -x "._*"
)

echo "[bundle] creating tar.gz: $TAR_PATH"
rm -f "$TAR_PATH"
(
  cd "$RELEASE_DIR"
  tar -czf "$(basename "$TAR_PATH")" "$(basename "$BUNDLE_DIR")"
)

echo "[bundle] done"
echo "[bundle] folder: $BUNDLE_DIR"
echo "[bundle] zip: $ZIP_PATH"
echo "[bundle] tar.gz: $TAR_PATH"
du -sh "$BUNDLE_DIR" "$ZIP_PATH" "$TAR_PATH"
