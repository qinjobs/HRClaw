# HRClaw Windows 一键安装包

这个目录已经是完整的自包含安装包，里面带着源码、安装脚本和 Windows 专用附件。直接把整个目录拷到 Windows 机器上，然后双击 `INSTALL.BAT` 就行。

这套目录是给 Windows 10 专用的安装入口。建议在机器上先把整套项目解压到一个稳定目录，例如：

```text
C:\RecruitingScreening\
```

然后双击：

```text
INSTALL.BAT
```

## 安装内容

- 自动安装本机 Python 3.12 运行时
- 自动创建 `.venv`
- 自动尝试安装第一阶段与第二阶段 OCR 依赖，单个 wheel 不可用时会继续安装主系统
- 自动安装 Playwright Chromium
- 自动恢复前端静态产物
- 自动生成默认 `.env.local`
- 自动启动本地服务

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

## 运行入口

- 登录页：`http://127.0.0.1:8080/login`
- JD评分卡：`http://127.0.0.1:8080/hr/phase2`
- 简历导入：`http://127.0.0.1:8080/hr/resume-imports`

## 维护脚本

- 启动服务：`start_server.bat`
- 停止服务：`stop_server.bat`
- 健康检查：`check_health.bat`
- 恢复前端静态产物：`restore_frontend_dist.ps1`
