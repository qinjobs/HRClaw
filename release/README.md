# HRClaw 发布清单

- 整理日期：2026-05-09
- 仓库版本：`v0.2.0`
- 产物来源：当前仓库正式打包脚本生成
  - `scripts/build_macos_tahoe_bundle.sh`
  - `scripts/build_macos_dmg.sh`
  - `scripts/build_windows_offline_bundle.sh`
  - `scripts/build_windows_installer_exe.sh`

## 1. 发布产物

| 平台 | 文件名 | 大小 | 产物时间 | 说明 |
| --- | --- | ---: | --- | --- |
| macOS | `HRClaw_macos_tahoe_arm64_installer.dmg` | `809128660` bytes / `771.65 MiB` | `2026-05-09 10:15:09` | 成品安装盘镜像，适用于 `macOS Tahoe 26+`、`Apple Silicon M1+` |
| macOS | `HRClaw_macos_tahoe_arm64_bundle.zip` | `803339768` bytes / `766.13 MiB` | `2026-05-09 10:14:04` | 离线 bundle 压缩包，便于内网分发 |
| macOS | `HRClaw_macos_tahoe_arm64_bundle.tar.gz` | `803319058` bytes / `766.11 MiB` | `2026-05-09 10:14:22` | 与 zip 内容一致，便于命令行分发 |
| Windows | `HRClaw_windows_offline_installer.exe` | `804581742` bytes / `767.31 MiB` | `2026-05-09 10:34:40` | 成品自解压安装器，首次运行会解压到 `%USERPROFILE%\\HRClaw_windows_offline_bundle` 并自动启动 `INSTALL.BAT` |
| Windows | `HRClaw_windows_offline_bundle.zip` | `849493959` bytes / `810.14 MiB` | `2026-05-09 10:15:56` | 适用于 `Windows 10/11 64-bit` 的离线 bundle 压缩包 |

## 2. SHA256

```text
d7a4e65fe015db210dfdd9e6e81b45d1d63a9421998ebf30fd069cdbee83d78a  HRClaw_macos_tahoe_arm64_installer.dmg
10c81f282a94da4bbce593089060722fb1923450b829b4ee9c409b9212f35f80  HRClaw_macos_tahoe_arm64_bundle.zip
ce601792c9aae02794d0d7d6ea5760c3bc0b96e55b6ef1e85d67c32662167682  HRClaw_macos_tahoe_arm64_bundle.tar.gz
580fe5fbe91220e6dba0ea4433cb8d838f741d1f0ee8f1df9c0222dfbefa2d01  HRClaw_windows_offline_installer.exe
6b5b284c256a233c06a5df6feed669970641b6b7c1c4df4fac5b78f2a84a6050  HRClaw_windows_offline_bundle.zip
```

## 3. 安装入口

### macOS

- 打开镜像：双击 `HRClaw_macos_tahoe_arm64_installer.dmg`
- 镜像内容：`HRClaw_macos_tahoe_arm64_bundle/`
- 根目录安装：`INSTALL.command`
- 启动服务：`START_SERVER.command`
- 停止服务：`STOP_SERVER.command`
- 健康检查：`CHECK_HEALTH.command`

### Windows

- 成品安装器：双击 `HRClaw_windows_offline_installer.exe`
- 默认解压目录：`%USERPROFILE%\HRClaw_windows_offline_bundle`
- 自动启动：`INSTALL.BAT`
- 手工启动服务：`START_SERVER.BAT`
- 手工停止服务：`STOP_SERVER.BAT`
- 手工健康检查：`CHECK_HEALTH.BAT`

## 4. 随包说明文档

- macOS 安装手册：`docs/HRClaw_Mac客户安装手册.md`
- Windows 安装手册：`docs/HRClaw_Windows客户安装手册.md`
- 电脑配置建议：`docs/HRClaw_个人电脑安装配置建议.md`
- 试点 SOP：`docs/HRClaw_试点SOP.md`

## 5. 当前前端版本说明

本次安装包已同步最新前端静态资源，安装包内前端归档已更新为当前构建：

- `dist/assets/index-B0FiOko3.js`
- `dist/assets/index-DzVAuqU5.css`

## 6. 仓库内路径

- macOS dmg：`release/HRClaw_macos_tahoe_arm64_installer.dmg`
- macOS zip：`release/HRClaw_macos_tahoe_arm64_bundle.zip`
- macOS tar.gz：`release/HRClaw_macos_tahoe_arm64_bundle.tar.gz`
- Windows exe：`release/HRClaw_windows_offline_installer.exe`
- Windows zip：`release/HRClaw_windows_offline_bundle.zip`
