# BOSS 简历打分插件使用说明

这是一个内部使用的 Chrome MV3 插件，面向 BOSS 招聘场景。

## 功能概览

- 识别当前打开的 BOSS 候选人详情页
- 自动把候选人详情同步到配置好的筛选后端
- 秒级展示 `JD 速览`
- 异步返回完整评分
- 支持 HR 在插件中保存跟踪状态

## 使用前提

### 1. 筛选后端服务已经启动

```bash
bash /Users/jobs/Documents/CODEX/ZHAOPIN/scripts/start_phase1_server.sh
```

### 2. BOSS 登录态已保存

首次使用前建议执行：

```bash
PYTHONPATH=. /Users/jobs/Documents/CODEX/ZHAOPIN/.venv/bin/python /Users/jobs/Documents/CODEX/ZHAOPIN/scripts/save_boss_storage_state.py
```

### 3. 服务健康检查正常

```bash
bash /Users/jobs/Documents/CODEX/ZHAOPIN/scripts/check_phase1_health.sh
```

## 安装步骤

1. 打开 `chrome://extensions`
2. 打开“开发者模式”
3. 点击“加载已解压的扩展程序”
4. 选择目录：
   `/Users/jobs/Documents/CODEX/ZHAOPIN/chrome_extensions/boss_resume_score`
5. 建议把扩展固定到工具栏，方便打开侧边栏
6. 打开插件侧边栏，在“后端地址”中填入真实服务地址

后端地址示例：

- 本机：`http://127.0.0.1:8080`
- 内网服务器：`http://192.168.1.88:8080`

## 日常使用流程

1. 打开 BOSS 候选人详情页
2. 打开插件侧边栏
3. 插件会自动识别并入库当前候选人
4. 页面上先显示 `JD 速览`
5. 后端返回完整评分后，侧边栏更新最终结果
6. HR 可直接修改“跟踪状态”、备注、沟通结果和下次跟进时间
7. 点击“保存状态”后写入后台数据库

## 跟踪状态

插件支持以下状态：

- 新入库
- 已评分
- 待复核
- 建议沟通
- 已沟通
- 待回复
- 待跟进
- 已邀约
- 面试已约
- 人才库
- 已淘汰
- 不再联系

保存后：

- 后台会记录该候选人的最新状态
- 状态会同步到 HR Workbench
- 自动评分不会再覆盖 HR 手工状态

## 注意事项

- 只在候选人详情页入库，不在推荐列表页入库
- 推荐列表页不会插入评分浮层
- 如果代码有更新，必须在 `chrome://extensions` 中手动点一次“刷新”
- 插件使用 `chrome.storage.session` 做会话级缓存，重启浏览器后缓存会清空
- 插件会把“后端地址”保存在浏览器本地配置中

## 常见问题

### 1. 插件不显示结果

- 确认后端服务已启动
- 确认插件里的“后端地址”配置正确
- 确认当前打开的是候选人详情页
- 刷新扩展后重试

### 2. 侧边栏无法保存状态

- 先确认候选人已经完成入库并显示 `候选人 ID`
- 再点击“保存状态”
- 如果状态仍不更新，刷新扩展后重试

### 3. 页面样式异常

- 当前版本不会在推荐列表页插入打分展示
- 如果仍看到旧浮层，刷新扩展并刷新页面即可

## 相关页面

请把下面的 `BASE_URL` 替换成你的真实后端地址，例如：

- `http://127.0.0.1:8080`
- `http://192.168.1.88:8080`

对应页面：

- `BASE_URL/login`
- `BASE_URL/hr/workbench`
- `BASE_URL/hr/checklist`
