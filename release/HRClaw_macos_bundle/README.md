# HRClaw macOS 26 安装包

这套安装入口面向 macOS 26 及后续版本。

## 使用方式

1. 将整套项目解压到一个稳定目录，例如：
   ```text
   ~/HRClaw/
   ```
2. 双击解压后根目录下的 `INSTALL.command`
   - 如果你是在源码树里直接操作，也可以运行 `install/macos/INSTALL.command`
3. 等待脚本完成依赖安装、前端静态产物恢复和本地服务启动
4. 打开浏览器访问：
   ```text
   http://127.0.0.1:8080/login
   ```

## 维护入口

- 启动服务：`install/macos/start_server.command`
- 停止服务：`install/macos/stop_server.command`
- 健康检查：`install/macos/check_health.command`

## 安装内容

- 自动创建 Python 虚拟环境
- 自动安装第一阶段依赖
- 自动安装 Playwright Chromium
- 自动恢复前端静态产物
- 自动创建默认 `.env.local`
- 自动启动本地服务

## 默认配置

macOS 版本默认采用本地优先模式：

- 浏览器自动化：`playwright`
- 模型字段提取：`false`
- 搜索向量：`hash`
- OCR：`auto`
- 内置评分卡种子：`false`

## 说明

- 如果系统弹出 Gatekeeper 提示，请先右键打开一次 `INSTALL.command`
- 如果机器没有安装 `python3`，请先通过 Homebrew 或 Python 官网安装
- OCR 为可选能力，如需启用可在安装后执行第二阶段脚本
