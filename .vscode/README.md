# VSCode 开发说明（HRClaw）

## 1. 文件清单

- `.vscode/settings.json`：解释器、测试、ESLint/TS、终端环境变量
- `.vscode/tasks.json`：后端/前端启动、测试、Chrome CDP、Windows 打包
- `.vscode/launch.json`：Python 与前端调试配置（含 Chrome 9222 附着版）
- `.vscode/extensions.json`：推荐扩展
- `HRClaw.code-workspace`：建议直接用这个工作区打开，默认带上推荐扩展与常用设置

## 2. 首次准备

1. 打开仓库根目录：`/Users/jobs/Documents/CODEX/ZHAOPIN`
2. 安装推荐扩展（VSCode 会根据 `extensions.json` 提示）
3. 复制环境变量：
   - `cp .env.local.example .env.local`
4. 运行任务：
   - `Phase1: bootstrap python env`
   - `Frontend: npm ci`

## 3. 常用运行方式

- 启动后端：
  - Task: `Phase1: start backend`
  - 或 Debug: `Python: HRClaw backend (8080)`
- 启动后端（强制附着已打开的 Chrome 9222）：
  - Task: `Phase1: start backend (attach Chrome 9222)`
  - Debug: `Python: HRClaw backend (8080, attach Chrome 9222)`
- 启动前端：
  - Task: `Frontend: dev`
  - 或 Debug: `Frontend: Vite dev server`
- 后端 + 前端一起跑：
  - Task: `Dev: backend + frontend`
  - 或 Compound: `HRClaw: backend + frontend`
- 后端（附着 9222）+ 前端一起跑：
  - Compound: `HRClaw: backend (attach 9222) + frontend`

## 4. 常用测试

- 全量 Python 单测：
  - Task: `Tests: python unittest`
  - 或 Debug: `Python: unittest (all)`
- 当前测试文件：
  - Debug: `Python: unittest (current file)`
- 插件侧测试：
  - Task: `Tests: extension plugin`

## 5. Recommend 附着模式（9222）

1. 启动 Chrome：
   - Task: `Chrome CDP: launch 9222`
2. 检查端口：
   - Task: `Chrome CDP: check 9222`
3. 启动后端（附着模式）：
   - Task: `Phase1: start backend (attach Chrome 9222)` 或 Debug: `Python: HRClaw backend (8080, attach Chrome 9222)`
4. 执行前快速检查：
   - Task: `Recommend: ready check (9222 + backend)`

## 6. 环境变量

- Kimi Key 放在项目根目录 `.env.local`：
  - `SCREENING_KIMI_CLI_API_KEY=...`
- 如需指定 Kimi Base URL：
  - `SCREENING_KIMI_CLI_BASE_URL=https://api.kimi.com/coding/v1`
- Windows 首次安装/更新运行时：
  - Task: `Windows: install/update runtime`

## 7. 打包

- Windows 离线包：
  - Task: `Bundle: Windows offline package`

## 8. 地址

- 后端健康检查：`http://127.0.0.1:8080/health`
- 后台登录页：`http://127.0.0.1:8080/login`
- 前端开发页（Vite）：`http://127.0.0.1:5173`
