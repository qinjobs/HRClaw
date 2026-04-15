# VSCode 开发说明（HRClaw）

## 1. 首次准备

1. 打开仓库根目录：`/Users/jobs/Documents/CODEX/ZHAOPIN`
2. 安装推荐扩展（VSCode 会根据 `extensions.json` 提示）
3. 复制环境变量：
   - `cp .env.local.example .env.local`
4. 运行任务：
   - `Phase1: bootstrap python env`
   - `Frontend: npm ci`

## 2. 常用运行方式

- 启动后端：
  - Task: `Phase1: start backend`
  - 或 Debug: `Python: HRClaw backend (8080)`
- 启动前端：
  - Task: `Frontend: dev`
  - 或 Debug: `Frontend: Vite dev server`
- 后端 + 前端一起跑：
  - Task: `Dev: backend + frontend`
  - 或 Compound: `HRClaw: backend + frontend`

## 3. 常用测试

- 全量 Python 单测：
  - Task: `Tests: python unittest`
  - 或 Debug: `Python: unittest (all)`
- 当前测试文件：
  - Debug: `Python: unittest (current file)`
- 插件侧测试：
  - Task: `Tests: extension plugin`

## 4. 地址

- 后端健康检查：`http://127.0.0.1:8080/health`
- 后台登录页：`http://127.0.0.1:8080/login`
- 前端开发页（Vite）：`http://127.0.0.1:5173`
