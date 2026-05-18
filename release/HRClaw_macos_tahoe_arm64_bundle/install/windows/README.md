# HRClaw Windows 10 / 11 离线安装包

这套目录是给 Windows 10 / Windows 11（64 位）准备的离线安装入口。  
建议先把整套项目解压到一个稳定目录，例如：

```text
C:\RecruitingScreening\
```

然后双击：

```text
install\windows\install.bat
```

默认是“离线优先”安装，不依赖公网。如果你确实需要允许脚本联网兜底，可手工执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File install\windows\install.ps1 -AllowNetworkFallback
```

## 安装内容

- 自动安装本机 Python 3.12 运行时
- 自动创建 `.venv`
- 自动尝试安装第一阶段与第二阶段 OCR 依赖，单个 wheel 不可用时会继续安装主系统
- 自动解压离线 `chrome-win64.zip` 到 `runtime\chrome\chrome-win64\chrome.exe`
- 自动恢复前端静态产物
- 自动生成默认 `.env.local`
- 自动启动本地服务
- 可选离线安装 `uv` 与 `kimi-cli`

## 数据策略

这版 Windows 安装包默认按“全新上线”处理，只保留 `admin` 管理员账号，不带任何历史业务数据：

- 任务 LIST：清空
- 评分卡：清空
- 简历数据：清空
- 打分数据：清空
- 默认管理员：`admin / admin`

安装时会自动清理运行态数据目录，并关闭内置评分卡种子，避免把旧任务和示例数据带到 Windows 机器上。

## 默认配置

Windows 版默认把这些能力打开成更稳妥的本地模式：

- 浏览器自动化：`playwright`
- 模型字段提取：`false`
- 搜索向量：`hash`
- OCR：`auto`
- 内置评分卡种子：`false`

这样即使机器没有 Kimi CLI、OpenAI Key 或本地大模型，也能先把基础业务跑起来。

如果需要启用本地 `kimi` 命令，再执行：

```text
install\windows\install_kimi_cli.bat
```

如需同时安装离线 `uv`：

```text
install\windows\install_uv.bat
```

## 离线包完整性检查

离线安装要求以下文件存在：

- `install\packages\windows\python-3.12.9-amd64.exe`
- `install\packages\windows\chrome-win64.zip`
- `install\packages\windows\wheelhouse\*.whl`
- `install\packages\windows\admin_frontend-dist.zip`
- `install\packages\windows\uv\uv-x86_64-pc-windows-msvc.zip`
- `install\packages\windows\kimi-cli\kimi_cli-1.35.0-py3-none-any.whl`
- `install\packages\windows\kimi-cli\requirements-kimi-cli-win-py312.txt`（仅运行时依赖，不包含 `kimi-cli` 本体）

## 运行入口

- 登录页：`http://127.0.0.1:8080/login`
- JD评分卡：`http://127.0.0.1:8080/hr/phase2`
- 简历导入：`http://127.0.0.1:8080/hr/resume-imports`

## 维护脚本

- 启动服务：`install\windows\start_server.bat`
- 停止服务：`install\windows\stop_server.bat`
- 健康检查：`install\windows\check_health.bat`
- 恢复前端静态产物：`install\windows\restore_frontend_dist.ps1`
- 安装 uv：`install\windows\install_uv.bat`
- 安装 kimi-cli：`install\windows\install_kimi_cli.bat`
