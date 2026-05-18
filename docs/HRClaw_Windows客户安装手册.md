# HRClaw Windows 客户安装手册

版本：2026-04-27

本文档面向最终客户、销售实施同学和现场支持同学，适用于 `HRClaw_windows_offline_bundle` 离线安装包。

适用范围：

- 操作系统：`Windows 10 Pro 64 位` 或 `Windows 11 Pro 64 位`
- 浏览器：`Google Chrome`
- 网络：可访问 `BOSS 直聘`，如需模型打分还需可访问 `Kimi API`

相关文档：

- [HRClaw_个人电脑安装配置建议](HRClaw_个人电脑安装配置建议.md)
- [HRClaw_客户版功能说明](HRClaw_客户版功能说明.md)

## 1. 客户收到的安装包

标准发包文件：

- `HRClaw_windows_offline_bundle.zip`

解压后目录内会包含以下主要入口：

- `INSTALL.BAT`
- `START_SERVER.BAT`
- `STOP_SERVER.BAT`
- `CHECK_HEALTH.BAT`
- `INSTALL_UV.BAT`
- `INSTALL_KIMI_CLI.BAT`

## 2. 安装前准备

安装前请先确认：

- 操作系统为 `Windows 10/11 专业版 64 位`
- 建议使用本机管理员账号执行安装
- 本机剩余磁盘空间不少于 `40 GB`
- 已安装或允许使用 `Google Chrome`
- 杀毒软件、Windows 安全中心不会拦截本地 Python、Chrome 和 PowerShell 脚本
- 如需启用模型打分，已准备 `Kimi API Key`

推荐交付配置：

- 内存：`16 GB` 及以上
- 磁盘可用空间：`80 GB` 及以上

## 3. 安装步骤

### 3.1 解压安装包

把整个压缩包完整解压到固定目录，建议使用：

```text
E:\HRClaw_windows_offline_bundle\
```

注意：

- 不要只解压其中一部分文件
- 不要把 `packages`、`src`、`admin_frontend` 等目录拆开
- 不建议放在桌面临时目录、压缩软件的预览目录或网盘同步临时目录

### 3.2 首次安装

双击根目录的：

```text
INSTALL.BAT
```

安装程序会自动完成以下动作：

- 检查并复用本机 `Python 3.12`
- 如本机没有合适 Python，则安装离线 Python 运行时
- 创建项目虚拟环境 `.venv`
- 离线安装项目依赖
- 恢复前端页面文件
- 解压离线 Chrome 运行时
- 自动创建 `.env.local`
- 默认不自动启动本地后台服务

首次安装通常需要几分钟，视电脑性能而定。

## 4. 安装完成后的访问地址

安装成功后，请先手工执行 `START_SERVER.BAT`，再浏览器访问：

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

- 启动服务：`START_SERVER.BAT`
- 停止服务：`STOP_SERVER.BAT`
- 健康检查：`CHECK_HEALTH.BAT`

推荐日常使用方式：

- 早上上班后双击 `START_SERVER.BAT`
- 使用完成后双击 `STOP_SERVER.BAT`
- 如果页面访问异常，先执行一次 `CHECK_HEALTH.BAT`

说明：

- `START_SERVER.BAT` 会先尝试启动一个固定 `9222` 端口的 Chrome
- Chrome 用户目录默认是：

```text
%USERPROFILE%\.hrclaw-chrome-cdp-9222
```

- 后端服务会强制附着这个 Chrome，用于执行推荐牛人流程

## 6. Kimi 打分配置

如客户需要启用模型打分，请修改安装目录根下的：

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

如本机尚未安装 `kimi-cli`，可双击：

```text
INSTALL_KIMI_CLI.BAT
```

说明：

- 安装包已经内置 `kimi-cli` 所需离线资源
- 未配置 `SCREENING_KIMI_CLI_API_KEY` 时，系统会回退为“模型服务暂时不可用”

## 7. Chrome 与推荐流程说明

Windows 版支持本地 Chrome 运行时和推荐任务执行。`START_SERVER.BAT` 会先拉起固定 `9222` 端口的 Chrome，再启动后台服务。推荐客户使用方式：

1. 先执行 `START_SERVER.BAT`
2. 等待 Chrome 自动打开
3. 在这个 Chrome 中登录 BOSS
4. 打开 BOSS 推荐页
5. 登录 HRClaw 后台
6. 回到 HRClaw 后台执行“推荐牛人简历分析”任务

如客户后续需要 `uv` 环境，也可执行：

```text
INSTALL_UV.BAT
```

## 8. 客户首次验收建议

建议首次安装完成后，按下面顺序验收：

1. 打开 `http://127.0.0.1:8080/login`，确认页面可访问
2. 登录后台，确认首页、JD 评分卡、简历导入页面正常
3. 新建一张测试 JD 评分卡
4. 导入 1 份 PDF 简历，确认可以完成解析和评分
5. 如启用 Kimi，确认不是“模型提取已回退”
6. 如需推荐流程，确认可在 BOSS 页面完成一次推荐任务测试

通过标准：

- 页面可访问
- 登录正常
- 简历可导入
- 评分可生成
- 推荐页任务可执行

## 9. 常见问题

### 9.1 双击安装脚本没有反应

优先检查：

- 是否被 Windows Defender、杀毒软件或 SmartScreen 拦截
- 是否完整解压了整个安装目录
- 是否在只读目录中运行

### 9.2 安装时提示 Python 相关错误

优先检查：

- 是否已安装 `Python 3.12`
- 是否存在旧 `.venv` 被其他终端、VSCode 或杀毒软件占用
- 是否使用了管理员权限

如遇 `.venv` 被锁定，可先关闭 VSCode、终端和安全软件对该目录的占用后重试。

### 9.3 页面打不开

优先按下面顺序排查：

1. 执行 `CHECK_HEALTH.BAT`
2. 如服务未启动，执行 `START_SERVER.BAT`
3. 如仍异常，先执行 `STOP_SERVER.BAT`，再重新启动

### 9.4 推荐页任务无法执行

优先检查：

- Chrome 是否已经打开
- 是否使用的是 `START_SERVER.BAT` 拉起的 Chrome
- 是否已经登录 BOSS
- 是否已经打开 BOSS 推荐页
- `http://127.0.0.1:9222/json/version` 是否可访问
- 网络是否可以正常访问 BOSS

### 9.5 打分提示“模型提取已回退”

通常是以下原因之一：

- `.env.local` 中未配置 `SCREENING_KIMI_CLI_API_KEY`
- 本机未执行 `INSTALL_KIMI_CLI.BAT`
- `Kimi API Key` 已失效
- 网络无法访问 `https://api.kimi.com`

## 10. 交付建议

发客户时，建议一起提供以下内容：

- `HRClaw_windows_offline_bundle.zip`
- 本文档：`HRClaw_Windows客户安装手册.md`
- `HRClaw_个人电脑安装配置建议.md`
- 一份客户专用 `.env.local` 配置模板

如果由销售或实施远程协助安装，建议现场重点帮客户确认 3 件事：

- `Kimi API Key` 是否已填好
- `http://127.0.0.1:8080/login` 是否可稳定访问
- Chrome 与 BOSS 推荐页流程是否可正常执行
