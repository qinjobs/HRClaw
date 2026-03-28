# Windows 安装包说明

这里存放 Windows 10 一键安装需要的 Windows 专属附件。

## 目录用途

- `.env.local.example`：Windows 默认环境变量模板
- `admin_frontend-dist.zip`：Windows 友好的后台静态产物
- `wheelhouse/`：可选的离线 Python 轮子缓存目录

## 默认数据策略

Windows 安装包按“全新上线”准备，只保留默认的 `admin` 管理员账号，不预置以下业务数据：

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
