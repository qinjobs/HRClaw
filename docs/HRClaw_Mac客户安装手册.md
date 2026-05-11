# HRClaw Mac 客户安装手册

版本：2026-04-27

本文档面向最终客户、销售实施同学和现场支持同学，适用于 `HRClaw_macos_tahoe_arm64_bundle` 安装包。

适用范围：

- 操作系统：`macOS Tahoe 26` 及以上
- 芯片：`Apple Silicon M1` 及以上
- 浏览器：`Google Chrome` 最新稳定版

相关文档：

- [HRClaw_个人电脑安装配置建议](HRClaw_个人电脑安装配置建议.md)
- [HRClaw_客户版功能说明](HRClaw_客户版功能说明.md)

## 1. 客户收到的安装包

标准发包建议使用以下任一文件：

- `HRClaw_macos_tahoe_arm64_bundle.zip`
- `HRClaw_macos_tahoe_arm64_bundle.tar.gz`

解压后目录内会包含以下主要入口：

- `INSTALL.command`
- `START_SERVER.command`
- `STOP_SERVER.command`
- `CHECK_HEALTH.command`

## 2. 安装前准备

安装前请先确认：

- 电脑为 `Apple M1 / M2 / M3 / M4` 芯片
- 系统版本为 `macOS Tahoe 26` 或更新版本
- 已安装 `Google Chrome`
- 本机剩余磁盘空间不少于 `40 GB`
- 网络可访问 `BOSS 直聘`
- 如需启用模型打分，已准备 `Kimi API Key`

推荐交付配置：

- 内存：`16 GB` 及以上
- 磁盘可用空间：`80 GB` 及以上

## 3. 安装步骤

### 3.1 解压安装包

将安装包完整解压到本地固定目录，建议使用：

```text
~/HRClaw_macos_tahoe_arm64_bundle
```

注意：

- 不要只解压其中一部分文件
- 不要把 `install`、`scripts`、`src` 目录拆开
- 不建议放在会自动清理的临时目录

### 3.2 首次安装

在 Finder 中双击根目录的：

```text
INSTALL.command
```

安装程序会自动完成以下动作：

- 检查当前电脑是否为 Apple Silicon
- 检查 `Python 3.12+`
- 自动创建 `.env.local`
- 自动安装项目基础依赖
- 自动恢复前端页面文件
- 默认不自动启动本地后台服务

首次安装通常需要几分钟，取决于本机网络和 Python 环境状态。

### 3.3 如果系统阻止打开

如 macOS 弹出“无法打开”或安全提示，请按以下方式处理：

1. 在 Finder 中右键 `INSTALL.command`
2. 点击“打开”
3. 在弹窗中再次点击“打开”

如果仍被阻止，请在“系统设置 -> 隐私与安全性”中允许本次打开。

## 4. 安装完成后的访问地址

安装成功后，请先手工执行 `START_SERVER.command`，再浏览器访问：

```text
http://127.0.0.1:8080/login
```

常用页面：

- 登录页：`http://127.0.0.1:8080/login`
- JD 评分卡：`http://127.0.0.1:8080/hr/phase2`
- 简历导入：`http://127.0.0.1:8080/hr/resume-imports`
- 任务执行：`http://127.0.0.1:8080/hr/tasks`
- 邮件采集：`http://127.0.0.1:8080/hr/email-ingest`

## 5. 日常使用入口

安装目录根目录已经提供维护脚本：

- 启动服务：`START_SERVER.command`
- 停止服务：`STOP_SERVER.command`
- 健康检查：`CHECK_HEALTH.command`

推荐日常使用方式：

- 早上上班后双击 `START_SERVER.command`
- 使用完成后双击 `STOP_SERVER.command`
- 如果页面访问异常，先执行一次 `CHECK_HEALTH.command`

## 6. Kimi 打分配置

如客户需要启用模型打分，请配置安装目录根下的：

```text
.env.local
```

至少确认以下配置：

```text
SCREENING_ENABLE_MODEL_EXTRACTION=true
SCREENING_EXTRACTION_PROVIDER=kimi_cli
SCREENING_KIMI_CLI_API_KEY=你的Kimi_API_Key
SCREENING_KIMI_CLI_BASE_URL=https://api.kimi.com/coding/v1
```

说明：

- 安装程序会自动检测本机的 `kimi-cli`
- 如果已检测到，会自动把 `SCREENING_KIMI_CLI_COMMAND` 写成绝对路径
- 如果没有检测到，系统会回退为“模型服务暂时不可用”

如需手工指定 `kimi-cli` 路径，可补充：

```text
SCREENING_KIMI_CLI_COMMAND=/Users/你的用户名/.local/bin/kimi
```

## 7. Chrome 与推荐流程说明

Mac 安装包默认会在启动服务时尝试拉起一个带 `9222` 端口的 Chrome，会话目录默认是：

```text
$HOME/.hrclaw-chrome-cdp-9222
```

这一行为用于支持：

- 推荐牛人简历分析
- 连接已登录的 BOSS 页面
- 复用本地 Chrome 会话

推荐客户使用方式：

1. 先启动 `START_SERVER.command`
2. 等待 Chrome 自动打开
3. 在这个 Chrome 中登录 BOSS
4. 打开 BOSS 推荐页
5. 回到 HRClaw 后台执行“推荐牛人简历分析”任务

## 8. 客户首次验收建议

建议首次安装完成后，按下面顺序验收：

1. 打开 `http://127.0.0.1:8080/login`，确认页面可访问
2. 登录后台，确认首页、JD 评分卡、简历导入页面正常
3. 新建一张测试 JD 评分卡
4. 导入 1 份 PDF 简历，确认可以完成解析和评分
5. 如启用 Kimi，确认不是“模型提取已回退”
6. 打开 BOSS，在 Chrome 中完成一次推荐页任务测试

通过标准：

- 页面可访问
- 登录正常
- 简历可导入
- 评分可生成
- 推荐页任务可执行

## 9. 常见问题

### 9.1 双击安装脚本没有反应

优先检查：

- 是否被 Gatekeeper 拦截
- 是否完整解压了整个安装目录
- 是否在只读目录中运行

### 9.2 提示 Python 版本过低

HRClaw Mac 版要求：

```text
Python 3.12+
```

如终端提示版本不足，可先安装：

```bash
brew install python@3.12
```

然后重新执行：

```bash
PYTHON_BIN=$(which python3.12) ./INSTALL.command
```

### 9.3 页面打不开

优先按下面顺序排查：

1. 执行 `CHECK_HEALTH.command`
2. 如服务未启动，执行 `START_SERVER.command`
3. 如仍异常，先执行 `STOP_SERVER.command`，再重新启动

### 9.4 推荐页任务无法执行

优先检查：

- Chrome 是否已经打开
- 是否在被 HRClaw 启动的 Chrome 中登录了 BOSS
- 是否已经打开 BOSS 推荐页
- 本地 `9222` 端口是否可用

### 9.5 打分提示“模型提取已回退”

通常是以下原因之一：

- `.env.local` 中未配置 `SCREENING_KIMI_CLI_API_KEY`
- 本机未正确安装 `kimi-cli`
- `SCREENING_KIMI_CLI_COMMAND` 路径不正确
- Kimi 账号或 API Key 已失效

## 10. 交付建议

发客户时，建议一起提供以下内容：

- `HRClaw_macos_tahoe_arm64_bundle.zip`
- 本文档：`HRClaw_Mac客户安装手册.md`
- `HRClaw_个人电脑安装配置建议.md`
- 一份客户专用 `.env.local` 配置模板

如果由销售或实施远程协助安装，建议现场重点帮客户确认 3 件事：

- `Kimi API Key` 是否已填好
- Chrome 是否能正常打开并登录 BOSS
- `http://127.0.0.1:8080/login` 是否可稳定访问
