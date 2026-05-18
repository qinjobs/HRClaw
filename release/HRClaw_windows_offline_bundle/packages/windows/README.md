# HRClaw Windows 10 / 11 离线安装包说明

这里存放 Windows 10 / 11 一键离线安装需要的 Windows 专属附件。

## 目录用途

- `.env.local.example`：Windows 默认环境变量模板
- `admin_frontend-dist.zip`：Windows 友好的后台静态产物
- `python-3.12.9-amd64.exe`：离线 Python 安装包
- `chrome-win64.zip`：离线 Chrome 安装包
- `wheelhouse/`：离线 Python 轮子缓存目录，包含安装依赖和 OCR 相关依赖（无需联网 pip）
- `uv/`：uv 的 Windows x64 离线安装包
- `kimi-cli/`：kimi-cli 的离线安装资源（含依赖包）

## 默认数据策略

HRClaw Windows 安装包按“全新上线”准备，只保留默认的 `admin` 管理员账号，不预置以下业务数据：

- 任务 LIST
- 评分卡
- 简历数据
- 打分数据
- 默认管理员：`admin / admin`

## 使用方式

安装脚本位于：

```text
install\windows\install.bat
```

脚本会优先使用本目录下的 Windows 专属附件，不需要再去手工翻找 macOS 的示例文件。

如果 `python-3.12.9-amd64.exe`、`chrome-win64.zip` 和 `wheelhouse/` 都存在，Windows 安装过程就不需要再额外下载 Python、Chrome 和 Python 依赖。

如需安装离线 `uv` 和 `kimi-cli`，可使用：

```text
install\windows\install_uv.bat
install\windows\install_kimi_cli.bat
```
