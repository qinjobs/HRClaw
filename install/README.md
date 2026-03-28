# install 目录说明

这里统一整理了项目第一阶段与第二阶段部署所需的安装材料、分发包和常用脚本。

## 1. 推荐使用顺序

1. 阅读完整手册：
   `/Users/jobs/Documents/CODEX/ZHAOPIN/docs/第一阶段第二阶段完整安装部署手册.md`
2. 如为公司内网上线，先对照：
   `/Users/jobs/Documents/CODEX/ZHAOPIN/docs/内网部署实施清单.md`
3. 如果部署到 Windows 10 单机，优先使用：
   `/Users/jobs/Documents/CODEX/ZHAOPIN/install/windows/README.md`
4. 执行第一阶段安装：
   `bash install/scripts/bootstrap_phase1_env.sh`
5. 如需第二阶段 OCR 和批量导入能力，再执行：
   `bash install/scripts/bootstrap_phase2_env.sh`
6. 准备配置：
   `cp install/packages/config/.env.local.example .env.local`
7. 启动服务：
   `bash install/scripts/start_server.sh`
8. 健康检查：
   `bash install/scripts/check_health.sh`

## 2. 目录结构

```text
install/
├── README.md
├── packages/
│   ├── chrome_extension/
│   ├── config/
│   ├── frontend/
│   ├── python/
│   └── windows/
├── scripts/
└── windows/
```

## 3. 目录说明

### `packages/python`

- `requirements-phase1.txt`：第一阶段基础依赖
- `requirements-phase2-ocr.txt`：第二阶段 OCR 依赖
- `requirements-phase2-search-optional.txt`：高级搜索增强依赖
- `wheels/`：平台相关 wheel 包

### `packages/config`

- `.env.local.example`：本机部署模板
- `.env.intranet.example`：内网部署模板

### `packages/frontend`

- `admin_frontend-dist.tgz`：后台页面静态产物
- `package.json` / `package-lock.json`：前端依赖清单

### `packages/windows`

- `.env.local.example`：Windows 默认环境变量模板
- `admin_frontend-dist.zip`：Windows 友好的后台页面静态产物
- `README.md`：Windows 安装包说明

### `packages/chrome_extension`

- `boss_resume_score/`：Chrome 插件已解压目录
- `boss_resume_score.zip`：Chrome 插件压缩包

### `scripts`

- `bootstrap_phase1_env.sh`
- `bootstrap_phase2_env.sh`
- `restore_frontend_dist.sh`
- `start_server.sh`
- `stop_server.sh`
- `check_health.sh`

### `windows`

- `install.ps1` / `install.bat`：Windows 一键安装入口
- `start_server.ps1` / `start_server.bat`：Windows 启动服务
- `stop_server.ps1` / `stop_server.bat`：Windows 停止服务
- `check_health.ps1` / `check_health.bat`：Windows 健康检查
- `restore_frontend_dist.ps1`：Windows 恢复前端静态产物

## 4. 说明

- 后台 React 构建产物已经打包好，默认不要求部署机重新安装前端依赖
- OCR 依赖中的 PaddlePaddle wheel 目前只附带了本机现成的 `macOS arm64` 版本
- 如果目标机器平台不同，请按目标平台补充对应 wheel 或在线安装
