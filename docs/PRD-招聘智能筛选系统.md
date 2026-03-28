# 招聘智能筛选系统 PRD（基于当前代码实现）

## 1. 文档信息
- 产品名称：招聘智能筛选系统（BOSS 本地自动化 + GPT 评分）
- 文档版本：v1.0（实现对齐版）
- 基线代码目录：`/Users/jobs/Documents/CODEX/ZHAOPIN`
- 对齐日期：2026-03-11
- 文档目的：将当前已完成代码能力沉淀为可执行 PRD，用于产品、技术、HR 统一认知与验收。

## 2. 背景与目标
### 2.1 背景
HR 在 BOSS 直聘进行搜索、点开候选人、阅读简历、下载或打招呼、再人工打分，重复操作多且标准不一致。

### 2.2 产品目标
- 通过本地 Playwright 自动完成候选人列表抓取与详情采集。
- 使用 GPT + 规则融合提取结构化字段。
- 用岗位评分卡对候选人进行量化评分与决策（推荐/复核/拒绝）。
- 提供 HR 复核清单页面，形成“自动筛选 -> 人工确认 -> 后续动作”的闭环。

### 2.3 成功指标（MVP）
- 单任务可稳定处理 `max_candidates` 设定数量的候选人（含分页去重）。
- 每个候选人生成：快照、结构化字段、评分、决策、证据。
- HR 可在 `/hr/checklist` 一页查看并复核。
- 任务过程日志可追踪（状态流转、候选人处理、失败原因）。

## 3. 用户角色与使用场景
- HR 操作员：配置任务、运行任务、查看评分与证据、执行复核。
- 招聘主管：查看任务产出质量、调阈值、看通过率/拒绝率。
- 运维/开发：维护选择器、登录态、模型调用稳定性与数据存储。

核心场景：
- 深度搜索（`deep_search`）：按关键词、城市、排序抓取候选人。
- 推荐流（`recommend`）：在推荐牛人页处理候选人，并可按阈值自动“打招呼”。

## 4. 产品范围
### 4.1 本期已实现（In Scope）
- 任务管理 API：创建任务、启动任务、查询任务、候选人列表、日志。
- 浏览器执行引擎：
  - `playwright` 本地浏览器自动化（主路径）
  - `openai` computer-use 适配器（实验路径）
  - `mock` 模拟路径（测试）
- BOSS 登录态复用：Playwright `storage_state` 保存与校验脚本。
- 候选人采集：
  - 列表抓取、分页、去重
  - 打开详情、抓文本、截图
  - 推荐流可尝试下载简历，失败时导出 `.txt` 回退
- 字段提取：GPT 提取 + 失败回退到启发式提取。
- 评分决策：4 岗位评分卡 + 硬性过滤 + 权重评分 + 阈值决策。
- HR 清单页：任务过滤、评分查看、截图/详情跳转。
- 数据持久化：SQLite + 本地截图/简历文件。

### 4.2 本期不包含（Out of Scope）
- 复杂筛选组件自动配置（多选标签、复杂弹层筛选）。
- 强鲁棒防风控绕过能力（验证码/安全校验自动通过）。
- 大规模并发调度、队列、分布式执行。
- 完整 BI 报表与多租户权限体系。

## 5. 功能需求（按模块）
## 5.1 任务与状态机
- 系统必须支持任务创建：`job_id/search_mode/sort_by/max_candidates/max_pages/search_config`。
- 系统必须支持状态机流转（如 `created -> ... -> completed/failed`）。
- 非法状态流转必须抛错并记录日志。

状态枚举（核心）：
- `created`
- `booting_browser`
- `logging_in`
- `opening_search_page`
- `configuring_filters`
- `scanning_candidate_list`
- `opening_candidate`
- `capturing_snapshot`
- `extracting_fields`
- `scoring_candidate`
- `awaiting_hr_review`
- `completed` / `failed` / `blocked`

## 5.2 浏览器采集
- 读取可配置选择器（环境变量 `||` 兜底链）。
- 支持搜索页与推荐页两套 frame 定位。
- 支持分页 `max_pages` 与 external_id 去重。
- 候选人详情必须产出 `page_text + screenshot_path + evidence_map`。

## 5.3 字段提取与融合
- 默认调用 Kimi CLI（`kimi-for-coding`）提取结构化字段；仅在显式切换 provider 时使用 OpenAI 兼容接口。
- 模型调用异常或配额不足时，自动回退启发式提取，任务不中断。
- 合并结果需生成 `normalized_fields`，以便评分引擎消费。

## 5.4 评分与决策
- 先跑硬性过滤（不通过直接 `reject`）。
- 通过后按岗位维度权重汇总总分（0-100）。
- 根据阈值输出 `recommend/review/reject`。
- 推荐流可按阈值尝试自动打招呼，并记录动作审计。

## 5.5 HR 复核与操作
- 提供 `GET /api/hr/checklist` 聚合视图。
- 提供 `POST /api/candidates/{id}/review` 记录复核动作。
- 提供 `POST /api/candidates/{id}/confirm-action` 记录确认类动作。
- 提供候选人详情与截图访问接口，便于证据核验。

## 6. 机器评分卡定义（当前实现）
## 6.1 QA 测试工程师 `qa_test_engineer_v1`
- 硬过滤：
  - `years_experience >= 3`
  - `testing_evidence = true`
- 权重：
  - `core_test_depth` 25
  - `tools_coverage` 20
  - `frontend_backend` 15
  - `defect_closure` 15
  - `industry_fit` 15
  - `analysis_logic` 10
- 阈值：
  - `recommend >= 80`
  - `review >= 60`
  - 其余 `reject`

## 6.2 Python 开发工程师 `py_dev_engineer_v1`
- 硬过滤：
  - `education_level in [bachelor/master/phd/本科/硕士/博士]`
  - `years_experience >= 3`
  - `linux_experience = true`
- 权重：
  - `python_engineering` 30
  - `linux_shell` 15
  - `java_support` 10
  - `middleware_stack` 20
  - `security_fit` 15
  - `analysis_design` 10
- 阈值：
  - `recommend >= 82`
  - `review >= 62`

## 6.3 文案审美质检 `caption_aesthetic_qc_v1`
- 硬过滤：
  - `media_caption_evidence = true`
  - `writing_sample = true`
- 权重：
  - `aesthetic_writing` 30
  - `film_art_theory` 15
  - `ai_annotation_qc` 20
  - `visual_domain_coverage` 15
  - `watching_volume` 5
  - `english` 5
  - `portfolio` 5
  - `gender_bonus` 5
- 阈值：
  - `recommend >= 80`
  - `review >= 60`
- 规则补充：
  - 若触发 `gender_bonus`，即便高分也强制降级为 `review` 并要求 HR 复核。

## 6.4 郑州 Caption AI 训练师 `caption_ai_trainer_zhengzhou_v1`
- 硬过滤：
  - `zhengzhou_intent = true`
  - `age >= 22`
  - `education_level in [统招大专/大专/专科/本科/硕士/博士]`
  - `full_time_education = true`
  - `graduation_year <= 2025`
- 权重：
  - `writing_naturalness` 35
  - `reading_rule_follow` 20
  - `visual_analysis` 15
  - `film_language` 10
  - `output_stability` 10
  - `ai_annotation_experience` 5
  - `long_term_stability` 5
- 阈值：
  - `recommend >= 80`
  - `review >= 65`

## 7. 数据与存储需求
### 7.1 结构化库（SQLite）
- 任务：`screening_tasks`
- 候选人：`candidates`
- 快照：`candidate_snapshots`
- 评分：`candidate_scores`
- 复核：`review_actions`
- 动作审计：`candidate_actions`
- 运行日志：`run_logs`

### 7.2 文件存储
- 数据库：`data/screening.db`
- 截图：`data/screenshots/<session_id>/...`
- 简历下载/回退文本：`data/resumes/<session_id>/...`
- 登录态：`data/auth/boss_storage_state.json`

### 7.3 审计要求
- 每个候选人至少保留：`raw_summary + screenshot + evidence_map + score + decision`。
- 对自动打招呼等动作必须存储动作状态和原因。

## 8. API 需求清单（当前已实现）
- `GET /health`
- `GET /api/jobs`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/start`
- `GET /api/tasks/{task_id}/candidates`
- `GET /api/tasks/{task_id}/logs`
- `GET /api/hr/checklist`
- `GET /hr/checklist`
- `GET /api/candidates/{candidate_id}`
- `GET /api/candidates/{candidate_id}/screenshot`
- `POST /api/candidates/{candidate_id}/review`
- `POST /api/candidates/{candidate_id}/confirm-action`

## 9. 非功能需求
- 稳定性：GPT 调用失败不能导致整任务中断（已支持回退）。
- 可观测性：关键流程节点必须写 `run_logs`。
- 可配置性：选择器、URL、阈值、模型均可通过环境变量修改。
- 安全性：
  - `OPENAI_API_KEY` 与 `storage_state` 属于敏感凭据。
  - 禁止将 `data/auth` 提交到公共仓库。

## 10. 验收标准（与测试用例对齐）
- API 流程：创建任务 -> 启动 -> 返回候选人（`tests/test_api.py`）。
- 状态机：合法流转通过，非法流转报错（`tests/test_state_machine.py`）。
- 评分卡：硬过滤、阈值、特殊规则正确（`tests/test_scoring.py`）。
- Playwright 采集：可抓取、可回退、可分页去重（`tests/test_playwright_agent.py`, `tests/test_pagination.py`）。
- 推荐流：下载、回退、自动打招呼逻辑正确（`tests/test_recommend_flow.py`）。
- HR 清单：聚合接口、截图接口、页面路由可用（`tests/test_hr_checklist.py`）。
- 日志接口：任务日志可查询（`tests/test_logs.py`）。

## 11. 当前版本限制与风险
- BOSS 页面结构变动会导致选择器失效，需要周期性校准。
- `storage_state` 不能保证永久免登录，安全校验触发后需重新保存。
- OpenAI computer-use 路径仍是实验能力，主线建议使用本地 Playwright。
- 当前服务是单进程同步执行，任务量大时需引入队列与异步调度。

## 12. 后续版本建议（PRD 预留）
- V1.1：抽离选择器配置中心、增加页面探针自动回归。
- V1.2：引入任务队列与并发 worker，支持批量任务编排。
- V1.3：增加 HR 反馈学习闭环（复核结果反哺评分策略）。
- V1.4：增加多岗位模板管理、报表与权限体系。
