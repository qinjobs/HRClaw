# HRClaw 个人电脑安装配置建议

版本：2026-04-26

本文档用于 HRClaw 客户试点、销售交付和售前确认。配置建议按“能安装运行”和“推荐销售交付”分开，优先保证客户现场安装顺利、Chrome 自动化稳定、简历解析和模型评分体验顺畅。

一句话建议：

- Windows 客户默认推荐：Windows 11 Pro 64 位 + 16 GB 内存 + SSD + Chrome 最新版。
- Mac 客户默认推荐：Apple Silicon M1 及以上 + macOS Tahoe 26 及以上 + 16 GB 内存 + Chrome 最新版。
- 扫描版 PDF OCR、批量简历导入、长期自动采集场景，建议直接上 32 GB 内存。

## 一、适用场景

HRClaw 当前个人电脑安装版主要运行以下能力：

- 本地后台管理平台
- Chrome 浏览器采集插件
- 推荐牛人简历分析
- PDF / DOC / DOCX 简历导入与评分
- 邮箱附件简历采集与定时评分
- Checklist 复核与推荐处理台
- Kimi CLI / API 调用模型进行结构化提取和评分

## 二、总体推荐

销售交付时，建议优先推荐客户使用近 3-5 年内的主流办公电脑。HRClaw 不强依赖独立显卡，但比较依赖内存、SSD、Chrome 稳定性和网络质量。

| 等级 | 使用场景 | 建议结论 |
|---|---|---|
| 最低可装 | 单人试用、少量简历测试 | 可运行，但不建议作为正式客户交付标准 |
| 推荐配置 | 客户试点、日常招聘筛选 | 默认销售推荐配置 |
| 高强度配置 | 批量简历、扫描版 PDF、多个 JD 并行测试 | 适合招聘量较大的 HR 团队 |

## 三、采购建议总表

| 客户场景 | Windows 推荐 | Mac 推荐 | 说明 |
|---|---|---|---|
| 销售演示 / 单人试用 | i5 / Ryzen 5，8-16 GB 内存，SSD 可用 40 GB | M1，8-16 GB 内存，SSD 可用 40 GB | 可完成演示和小批量验证 |
| HR 日常使用 | i5 / i7 第 10 代及以上，16 GB 内存，SSD 可用 80 GB | M1/M2/M3/M4，16 GB 内存，SSD 可用 80 GB | 推荐作为客户默认采购标准 |
| 批量简历 / OCR / 长时间采集 | i7 / Ryzen 7 及以上，32 GB 内存，SSD 可用 120 GB | M2 Pro/M3 Pro/M4 Pro 或以上，32 GB 内存，SSD 可用 120 GB | 适合扫描版简历多、批量任务多的客户 |

## 四、Windows 电脑配置

### 4.1 支持范围

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10 专业版 64 位或 Windows 11 专业版 64 位 |
| 推荐系统 | Windows 11 Pro 64 位 |
| 浏览器 | Google Chrome 最新稳定版 |
| 权限 | 本机管理员权限，允许运行本地安装脚本 |
| 网络 | 能访问 BOSS 直聘、Kimi / 模型 API 服务 |

注意：Microsoft 官方 Windows 11 最低要求为 1 GHz 双核、4 GB RAM、64 GB 存储、UEFI/Secure Boot、TPM 2.0。HRClaw 的推荐配置高于官方最低要求，是为了保证 Chrome 自动化、模型调用、文件解析和 OCR 体验稳定。

Windows 10 说明：HRClaw 安装包可以面向 Windows 10 专业版 64 位客户交付，但截至 2026-04-26，普通 Windows 10 官方支持已在 2025-10-14 结束。销售和实施时应优先推荐 Windows 11 Pro；如客户坚持 Windows 10，应由客户确认内部安全补丁和终端管控策略。

### 4.2 最低可装配置

| 项目 | 最低配置 |
|---|---|
| CPU | Intel i5 第 8 代 / AMD Ryzen 5 3000 系列或同等级以上 |
| 内存 | 8 GB |
| 硬盘 | SSD，剩余空间不低于 20 GB |
| 系统 | Windows 10 Pro 64 位 |
| 屏幕 | 1366 x 768 以上 |
| 浏览器 | Chrome，支持远程调试端口 9222 |

说明：最低配置适合演示和小批量测试。若客户需要扫描版 PDF OCR、批量导入简历或长时间运行自动采集，8 GB 内存容易出现卡顿。

### 4.3 推荐销售配置

| 项目 | 推荐配置 |
|---|---|
| CPU | Intel i5 / i7 第 10 代及以上，或 AMD Ryzen 5 / Ryzen 7 4000 系列及以上 |
| 内存 | 16 GB |
| 硬盘 | SSD，剩余空间不低于 80 GB |
| 系统 | Windows 11 Pro 64 位，或 Windows 10 Pro 64 位 |
| 屏幕 | 1920 x 1080 以上 |
| 网络 | 稳定宽带，建议不低于 20 Mbps |
| 浏览器 | Chrome 最新稳定版 |

这是默认推荐给客户采购、试点和正式使用的配置。

### 4.4 高强度配置

| 项目 | 高强度配置 |
|---|---|
| CPU | Intel i7 / i9 第 12 代及以上，或 AMD Ryzen 7 / Ryzen 9 5000 系列及以上 |
| 内存 | 32 GB |
| 硬盘 | SSD，剩余空间不低于 120 GB |
| 系统 | Windows 11 Pro 64 位 |
| 屏幕 | 1920 x 1080 或 2K 以上 |
| 网络 | 稳定宽带，建议不低于 50 Mbps |

适用于每天批量处理较多简历、扫描版 PDF 较多、同时测试多个 JD 评分卡、或需要长期运行推荐牛人分析流程的客户。

### 4.5 Windows 安装前检查

| 检查项 | 标准 |
|---|---|
| 系统版本 | Windows 10 / 11 专业版 64 位 |
| 磁盘空间 | 推荐至少 80 GB 可用空间 |
| 安装权限 | 当前账号具备管理员权限 |
| 杀毒软件 | 不拦截本地 Python、Chrome、脚本启动 |
| Chrome | 已安装，或使用 HRClaw 离线包内置 Chrome |
| 端口 | 本地 8080、9222 未被占用 |
| 网络 | 可访问 BOSS、模型 API |
| API Key | 已准备 Kimi / 模型服务 Key |

## 五、Mac 电脑配置

### 5.1 支持范围

| 项目 | 要求 |
|---|---|
| 芯片 | Apple Silicon，M1 及以上 |
| 操作系统 | macOS Tahoe 26 及以上优先 |
| 推荐系统 | macOS Tahoe 26.4.1 或更新版本 |
| 浏览器 | Google Chrome 最新稳定版 |
| 权限 | 可运行本地 `.command` 脚本，允许 Chrome 使用 9222 端口 |
| 网络 | 能访问 BOSS 直聘、Kimi / 模型 API 服务 |

说明：Apple 官方 macOS Tahoe 26 兼容列表中包含部分 Intel Mac，但 HRClaw 面向客户交付时建议统一按 Apple Silicon M1 以上作为销售标准，减少本地依赖、离线包架构和 OCR 兼容问题。

截至 2026-04-26，Apple 官方列出的 macOS Tahoe 当前最新版本为 26.4.1。客户电脑如果是 26.3.1 也可以作为试点环境，但正式交付建议升级到 26.4.1 或更新版本。

### 5.2 最低可装配置

| 项目 | 最低配置 |
|---|---|
| 机型 | MacBook Air / MacBook Pro / Mac mini，Apple M1 及以上 |
| 内存 | 8 GB |
| 硬盘 | 剩余空间不低于 20 GB |
| 系统 | macOS Tahoe 26 及以上 |
| 浏览器 | Chrome，支持远程调试端口 9222 |

说明：M1 + 8 GB 内存可以用于单人试用和演示，但扫描版 PDF、批量导入、多个页面并行时可能不够流畅。

### 5.3 推荐销售配置

| 项目 | 推荐配置 |
|---|---|
| 机型 | MacBook Air M2/M3/M4，MacBook Pro M1 Pro 及以上，Mac mini M2/M4 及以上 |
| 内存 | 16 GB |
| 硬盘 | 剩余空间不低于 80 GB |
| 系统 | macOS Tahoe 26.4.1 或更新版本 |
| 屏幕 | 13 英寸以上，建议外接显示器 |
| 网络 | 稳定宽带，建议不低于 20 Mbps |

这是 Mac 客户试点和正式交付的推荐配置。

### 5.4 高强度配置

| 项目 | 高强度配置 |
|---|---|
| 机型 | MacBook Pro M2 Pro/M3 Pro/M4 Pro 及以上，或 Mac Studio |
| 内存 | 32 GB |
| 硬盘 | 剩余空间不低于 120 GB |
| 系统 | macOS Tahoe 26.4.1 或更新版本 |
| 网络 | 稳定宽带，建议不低于 50 Mbps |

适用于招聘量大、批量简历多、扫描版 PDF 较多、需要长期打开 Chrome 会话并持续运行自动采集的客户。

### 5.5 Mac 安装前检查

| 检查项 | 标准 |
|---|---|
| 芯片 | Apple M1 / M2 / M3 / M4 及以上 |
| 系统版本 | macOS Tahoe 26 及以上 |
| 磁盘空间 | 推荐至少 80 GB 可用空间 |
| Chrome | 已安装 Google Chrome |
| 端口 | 本地 8080、9222 未被占用 |
| 权限 | 允许打开 `.command` 脚本 |
| 网络 | 可访问 BOSS、模型 API |
| API Key | 已准备 Kimi / 模型服务 Key |

## 六、销售推荐口径

### 6.1 默认推荐

Windows 客户优先推荐：

- Windows 11 Pro 64 位
- Intel i5 第 10 代以上或同等级 AMD
- 16 GB 内存
- SSD 剩余 80 GB 以上
- Chrome 最新版

Mac 客户优先推荐：

- Apple Silicon M1 及以上
- macOS Tahoe 26 及以上
- 16 GB 内存
- SSD 剩余 80 GB 以上
- Chrome 最新版

### 6.2 可直接对客户说的话

HRClaw 不需要客户单独购买服务器，也不需要独立显卡。常规试点准备一台 16 GB 内存、SSD、可安装 Chrome 的办公电脑即可。若客户扫描版简历较多、需要批量导入或长期自动采集，建议使用 32 GB 内存机器，体验会明显更稳。

### 6.3 不建议交付的电脑

- Windows 7 / Windows 8 / 32 位 Windows
- 机械硬盘为主盘的旧电脑
- 4 GB 内存电脑
- 无法安装或打开 Chrome 的电脑
- 公司策略禁止本地脚本、禁止本地端口、禁止浏览器插件的电脑
- 网络无法访问 BOSS 或模型 API 的电脑

## 七、客户现场快速确认表

| 问题 | 合格标准 |
|---|---|
| 电脑系统是什么？ | Windows 10/11 Pro 64 位，或 macOS Tahoe 26+ |
| 内存是多少？ | 推荐 16 GB 以上 |
| 磁盘剩余空间是多少？ | 推荐 80 GB 以上 |
| 是否已安装 Chrome？ | 是 |
| 是否能登录 BOSS？ | 是 |
| 是否允许安装 Chrome 插件？ | 是 |
| 是否允许运行本地服务？ | 是，本地 8080 可用 |
| 是否允许 Chrome 远程调试端口？ | 是，本地 9222 可用 |
| 是否已准备模型 API Key？ | 是 |

## 八、参考来源

- Microsoft Windows 11 官方最低系统要求：<https://support.microsoft.com/en-us/windows/windows-11-system-requirements-86c11283-ea52-4782-9efd-7674389a7ba3>
- Apple macOS Tahoe 26 官方兼容机型列表：<https://support.apple.com/en-lamr/122867>
- Apple 官方 macOS 最新版本列表：<https://support.apple.com/en-us/109033>
- Google Chrome 官方系统要求：<https://support.google.com/chrome/a/answer/7100626>
