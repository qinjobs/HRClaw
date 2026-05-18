# kimi-cli 离线安装资源（Windows + Python 3.12）

本目录存放 `kimi-cli` 的离线安装资源，供 Windows 客户机直接使用：

- `kimi_cli-1.35.0-py3-none-any.whl`
- `requirements-kimi-cli-win-py312.txt`（仅运行时依赖，不包含 `kimi-cli` 自身）
- 该版本依赖的 Windows wheel 集合
- `ripgrepy-2.2.0.tar.gz`（源码包，配合本地 `setuptools/wheel` 安装）

推荐通过项目脚本安装（先执行主安装）：

```text
install\windows\install_kimi_cli.bat
```

说明：

- 默认离线安装，不访问公网。
- `kimi-cli` 本体通过 `--no-deps` 安装，避免拉入 `fastmcp/openapi` 依赖链。
- 如需联网兜底，可追加参数：`-AllowNetworkFallback`。
