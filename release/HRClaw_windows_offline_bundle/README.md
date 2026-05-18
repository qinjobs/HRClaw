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
