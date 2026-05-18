# HRClaw macOS 安装包（Tahoe 26+ / Apple Silicon）

这套目录提供给 macOS Tahoe 26 及后续版本使用，推荐 Apple Silicon（M1 及以上）设备。

## 使用方式

1. 将整套项目解压到一个稳定目录，例如：
   ```text
   ~/HRClaw/
   ```
2. 双击 `install/macos/INSTALL.command`
3. 等待脚本完成依赖安装和前端静态产物恢复
4. 手工执行 `install/macos/start_server.command`
5. 打开浏览器访问：
   ```text
   http://127.0.0.1:8080/login
   ```

## 安装内容

- 自动创建 Python 虚拟环境
- 自动安装第一阶段依赖
- 自动安装 Playwright Chromium
- 自动恢复前端静态产物
- 自动创建默认 `.env.local`
- 默认不自动启动本地服务

## 默认配置

macOS 版本默认采用本地优先模式：

- 浏览器自动化：`playwright`
- 模型字段提取：`true`（默认走 `kimi_cli`）
- 搜索向量：`hash`
- OCR：`auto`
- 内置评分卡种子：`false`

## Kimi CLI 配置

如需启用模型打分，请确认下面两项至少满足一项：

1. 在 `.env.local` 中配置：
   ```text
   SCREENING_KIMI_CLI_API_KEY=你的 Kimi API Key
   SCREENING_KIMI_CLI_BASE_URL=https://api.kimi.com/coding/v1
   ```
2. 或先在终端执行：
   ```bash
   kimi login
   ```
   让 `kimi-cli` 生成 `~/.kimi/config.toml`

如果你是通过 Finder 双击启动服务，建议把 `.env.local` 里的 `SCREENING_KIMI_CLI_COMMAND` 改成绝对路径，例如：

```text
SCREENING_KIMI_CLI_COMMAND=/Users/你的用户名/.local/bin/kimi
```

## 维护脚本

- 启动服务：`install/macos/start_server.command`
- 停止服务：`install/macos/stop_server.command`
- 健康检查：`install/macos/check_health.command`

## 说明

- 如果系统弹出 Gatekeeper 提示，请先右键打开一次 `INSTALL.command`
- 推荐预装 `python3.12`（未安装时脚本会自动尝试 `python3`）
- OCR 为可选能力，如需启用可在安装后执行第二阶段脚本
