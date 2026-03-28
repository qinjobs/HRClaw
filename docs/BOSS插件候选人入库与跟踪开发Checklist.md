# BOSS 插件候选人入库与跟踪开发 Checklist

## 1. 文档目标

- 文档名称：BOSS 插件候选人入库与跟踪开发 Checklist
- 适用范围：`BOSS 简历打分` Chrome 插件 + 本地筛选后端 + HR workbench
- 当前基线目录：`/Users/jobs/Documents/CODEX/ZHAOPIN`
- 主流程定义：`识别到候选人详情页 -> 自动入库 -> 本地 JD 速览 -> 异步完整打分 -> HR 标记跟踪状态 -> HR 后台查询管理`

## 2. 本期目标

- 候选人进入 BOSS 详情页时自动入库，不依赖 HR 手动点击打分。
- 插件侧支持标记跟踪状态：
  - `新入库`
  - `已评分`
  - `待复核`
  - `建议沟通`
  - `已沟通`
  - `待回复`
  - `待跟进`
  - `已邀约`
  - `面试已约`
  - `人才库`
  - `已淘汰`
  - `不再联系`
- HR 后台支持按来源、状态、负责人、跟进时间筛选，并管理候选人状态。
- 自动流程不得覆盖 HR 已手动修改的状态。

## 3. 现有能力复用

### 3.1 现有表

- `candidates`
- `candidate_snapshots`
- `candidate_scores`
- `candidate_pipeline_state`
- `candidate_timeline_events`
- `screening_tasks`

### 3.2 现有接口与代码基础

- 阶段枚举与中文映射：`src/screening/api.py`
- workbench 列表接口：`GET /api/hr/workbench`
- 候选人状态更新接口：`POST /api/candidates/{candidate_id}/stage`
- 插件打分入口：`POST /api/extension/score`
- 插件现有侧边栏与 worker：
  - `chrome_extensions/boss_resume_score/sidepanel.js`
  - `chrome_extensions/boss_resume_score/service-worker.js`

## 4. 总体方案

### 4.1 触发时机

- 插件在后台识别到“稳定的候选人详情页”后立即执行入库。
- 稳定判定建议：
  - `isDetail = true`
  - 不是推荐列表页
  - 上下文稳定 `500-800ms`
  - `page_text` 长度达到最小阈值

### 4.2 自动流程

1. 识别到候选人详情页
2. 插件自动调用 `upsert` 入库接口
3. 返回 `candidate_id`
4. 插件展示 `已入库`
5. 插件本地渲染 `JD 速览`
6. 插件异步调用完整评分接口
7. 若当前阶段仍为 `new`，自动推进到 `scored`
8. HR 在插件或后台手动改状态后，后续自动流程只更新快照和评分，不改人工状态

### 4.3 状态映射

| 展示状态 | 底层阶段 |
|---|---|
| 新入库 | `new` |
| 已评分 | `scored` |
| 待复核 | `to_review` |
| 建议沟通 | `to_contact` |
| 已沟通 | `contacted` |
| 待回复 | `awaiting_reply` |
| 待跟进 | `needs_followup` |
| 已邀约 | `interview_invited` |
| 面试已约 | `interview_scheduled` |
| 人才库 | `talent_pool` |
| 已淘汰 | `rejected` |
| 不再联系 | `do_not_contact` |

说明：
- “新入库已评分”不新增数据库枚举，前端可展示为“新入库，已评分”。

## 5. SQL 迁移 Checklist

### 5.1 必做

- [ ] 为 `candidate_pipeline_state` 增加 `manual_stage_locked integer not null default 0`
- [ ] 为 `candidate_pipeline_state` 增加人工锁索引
- [ ] 新增 `extension_candidate_bindings` 表
- [ ] 为 `extension_candidate_bindings` 增加唯一键：`(job_id, source, source_candidate_key)`
- [ ] 为 `extension_candidate_bindings` 增加按 `candidate_id`、`external_id`、`task_id` 的索引
- [ ] 为 `candidates` 增加 `source text not null default 'pipeline'`
- [ ] 为 `candidates(source, created_at)` 增加索引

### 5.2 建议 SQL 草案

```sql
alter table candidate_pipeline_state
add column manual_stage_locked integer not null default 0;

create index if not exists idx_candidate_pipeline_manual_lock
on candidate_pipeline_state(manual_stage_locked, updated_at);

create table if not exists extension_candidate_bindings (
    id text primary key,
    candidate_id text not null,
    job_id text not null,
    task_id text not null,
    source text not null,
    source_candidate_key text not null,
    external_id text,
    page_url text,
    latest_text_hash text not null,
    first_seen_at text not null default current_timestamp,
    last_seen_at text not null default current_timestamp,
    last_scored_at text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique(job_id, source, source_candidate_key)
);

create index if not exists idx_ext_bindings_candidate
on extension_candidate_bindings(candidate_id, updated_at);

create index if not exists idx_ext_bindings_external
on extension_candidate_bindings(job_id, external_id, updated_at);

create index if not exists idx_ext_bindings_task
on extension_candidate_bindings(task_id, updated_at);

alter table candidates
add column source text not null default 'pipeline';

create index if not exists idx_candidates_source_created
on candidates(source, created_at);
```

### 5.3 迁移验收

- [ ] 旧数据迁移后不影响现有任务流
- [ ] `GET /api/hr/workbench` 旧查询仍可返回结果
- [ ] 不新增截图 BLOB 存储，继续沿用 `candidate_snapshots.screenshot_path`

## 6. 后端接口 Checklist

### 6.1 `POST /api/extension/candidates/upsert`

用途：打开候选人详情页即入库。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `job_id` | `string` | 是 | 岗位 ID |
| `source` | `string` | 是 | 固定 `boss_extension_v1` |
| `source_candidate_key` | `string` | 是 | 幂等键 |
| `external_id` | `string` | 否 | BOSS 候选人 ID |
| `page_url` | `string` | 是 | 当前详情 URL |
| `page_title` | `string` | 否 | 页面标题 |
| `page_text` | `string` | 是 | 详情全文 |
| `candidate_name` | `string` | 否 | 页面识别出的姓名 |
| `page_type` | `string` | 是 | 固定 `boss_resume_detail` |
| `observed_at` | `string` | 是 | ISO 时间 |
| `context_key` | `string` | 是 | 页面上下文指纹 |
| `quick_fit_payload` | `object` | 否 | 本地速览摘要 |

响应字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `candidate_id` | `string` | 候选人 ID |
| `task_id` | `string` | 插件来源 task |
| `created_new` | `boolean` | 是否首次入库 |
| `pipeline_state` | `object` | 当前状态 |
| `latest_snapshot_id` | `string` | 最新快照 ID |
| `manual_stage_locked` | `boolean` | 是否人工锁定 |

Checklist：

- [ ] 增加入参校验
- [ ] 支持按 `external_id` 优先去重
- [ ] `external_id` 缺失时按 `source_candidate_key` 去重
- [ ] 自动创建或获取插件专用 `screening_task`
- [ ] 首次入库时写入 `pipeline_state.current_stage = new`
- [ ] 重复打开时只更新 `last_seen_at` 和最新快照
- [ ] 写入 timeline：`extension_ingested` 或 `extension_snapshot_updated`

### 6.2 `GET /api/extension/candidates/lookup`

用途：插件判断当前候选人是否已入库。

请求参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `job_id` | `string` | 是 | 岗位 ID |
| `external_id` | `string` | 否 | 优先 |
| `source_candidate_key` | `string` | 否 | 兜底 |

响应字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `found` | `boolean` | 是否已入库 |
| `candidate_id` | `string` | 候选人 ID |
| `pipeline_state` | `object` | 当前状态 |
| `last_scored_at` | `string` | 最近评分时间 |

Checklist：

- [ ] 支持按 `job_id + external_id` 查询
- [ ] 支持按 `job_id + source_candidate_key` 查询
- [ ] 返回当前状态与最近评分时间

### 6.3 `POST /api/extension/candidates/{candidate_id}/score`

用途：候选人已入库后异步补完整打分。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `job_id` | `string` | 是 | 岗位 ID |
| `page_url` | `string` | 是 | 页面 URL |
| `page_title` | `string` | 否 | 页面标题 |
| `page_text` | `string` | 是 | 页面全文 |
| `candidate_hint` | `string` | 否 | 姓名或候选人提示 |
| `source` | `string` | 是 | 固定 `boss_extension_v1` |

响应字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `candidate_id` | `string` | 候选人 ID |
| `score` | `number` | 总分 |
| `decision` | `string` | 决策 |
| `dimension_scores` | `object` | 维度分 |
| `review_reasons` | `array` | 复核原因 |
| `hard_filter_fail_reasons` | `array` | 硬性失败原因 |
| `fallback_used` | `boolean` | 是否降级 |
| `state_transition` | `object` | 自动状态推进结果 |

Checklist：

- [ ] 复用现有评分逻辑
- [ ] 评分结果写入 `candidate_scores`
- [ ] 更新 `extension_candidate_bindings.last_scored_at`
- [ ] 若 `manual_stage_locked=0` 且当前阶段是 `new`，自动推进为 `scored`
- [ ] 若已人工接管状态，禁止自动覆盖
- [ ] 写入 timeline：`extension_scored`

### 6.4 复用 `POST /api/candidates/{candidate_id}/stage`

Checklist：

- [ ] 插件调用此接口时统一传 `operator=boss_extension_hr`
- [ ] 任何人工改状态操作都自动设置 `manual_stage_locked=1`
- [ ] 支持备注、负责人、跟进时间、联系结果
- [ ] 写入 timeline：`stage_updated`

### 6.5 扩展 `GET /api/hr/workbench`

Checklist：

- [ ] 增加 `source` 过滤
- [ ] 增加 `manual_stage_locked` 过滤
- [ ] 返回 `source`
- [ ] 返回 `manual_stage_locked`
- [ ] 返回最新快照时间与最近评分时间

## 7. Repository / Service Checklist

### 7.1 Repository

- [ ] 新增 `get_or_create_extension_task(job_id)`
- [ ] 新增 `get_extension_candidate_binding(job_id, source, source_candidate_key)`
- [ ] 新增 `get_extension_candidate_binding_by_external_id(job_id, source, external_id)`
- [ ] 新增 `upsert_extension_candidate_binding(...)`
- [ ] 新增 `insert_extension_candidate_snapshot(...)`
- [ ] 扩展 `upsert_candidate_pipeline_state(...)` 支持 `manual_stage_locked`
- [ ] 扩展 workbench 查询 join `candidates.source`

### 7.2 Service

- [ ] 新增 `ExtensionCandidateIngestService`
- [ ] 新增 `build_source_candidate_key(...)`
- [ ] 新增 `hash_page_text(...)`
- [ ] 评分服务支持按 `candidate_id` 回写
- [ ] 评分后自动推进 `new -> scored` 的服务逻辑

## 8. 插件前端 Checklist

### 8.1 `service-worker.js`

- [ ] 在识别到稳定详情页后自动触发 `upsert`
- [ ] 不依赖 side panel 打开状态
- [ ] 缓存 `contextKey -> candidate_id`
- [ ] 入库成功后广播 `candidate_id/current_stage`
- [ ] 自动异步触发 `score`
- [ ] 对快速切换候选人做 `selectionEpoch` 防串写
- [ ] 推荐列表页不触发入库
- [ ] 详情页切换时旧候选人结果不覆盖新候选人

### 8.2 `sidepanel.html`

- [ ] 新增“入库与跟踪”卡片
- [ ] 增加 `已入库/未入库` 显示
- [ ] 增加“跟踪状态”下拉
- [ ] 增加“备注”输入框
- [ ] 增加“下次跟进时间”输入框
- [ ] 增加“保存状态”按钮

### 8.3 `sidepanel.js`

- [ ] 接收入库结果并展示 `candidate_id`
- [ ] 候选人切换时立即清空旧状态显示
- [ ] 入库成功后展示“已入库，等待评分”或“已入库，已评分”
- [ ] 状态下拉使用统一中文文案
- [ ] 保存状态时调用 `POST /api/candidates/{candidate_id}/stage`
- [ ] `待跟进` 状态展示并提交 `next_follow_up_at`
- [ ] `已沟通/待回复` 支持提交 `last_contact_result`
- [ ] `人才库` 支持 `talent_pool_status`
- [ ] `已淘汰/不再联系` 支持 `reason_code/reason_notes`

### 8.4 `shared.js`

- [ ] 维护统一状态文案映射
- [ ] 增加来源文案：`boss_extension`
- [ ] 本地缓存键支持 `jobId + candidate_id`

## 9. HR 后台 Checklist

### 9.1 列表页

- [ ] 增加来源筛选：`插件入库 / 任务采集`
- [ ] 增加状态锁筛选：`人工接管 / 自动状态`
- [ ] 增加列：来源、最新入库时间、状态更新时间、最近评分时间
- [ ] 支持按状态、负责人、跟进时间筛选插件候选人

### 9.2 详情页

- [ ] 展示插件来源标识
- [ ] 展示最新简历文本快照
- [ ] 展示最新评分结果
- [ ] 展示当前跟踪状态
- [ ] 展示状态变更时间线

### 9.3 Timeline

- [ ] `extension_ingested`
- [ ] `extension_snapshot_updated`
- [ ] `extension_scored`
- [ ] `stage_updated`
- [ ] `follow_up_scheduled`

## 10. 自动状态保护 Checklist

- [ ] 自动入库只写 `new`
- [ ] 自动评分只允许 `new -> scored`
- [ ] 一旦 HR 手动改状态，设置 `manual_stage_locked=1`
- [ ] `manual_stage_locked=1` 后自动流程不能改 `current_stage`
- [ ] 自动流程仍允许更新快照、评分和最近访问时间

## 11. 测试 Checklist

### 11.1 后端单测

- [ ] 新候选人首次入库成功
- [ ] 同一候选人同一 JD 重复打开不重复建档
- [ ] 同一候选人不同 JD 分开建档
- [ ] 自动创建插件 task 成功
- [ ] `upsert` 正确写入快照
- [ ] `score` 正确写入分数
- [ ] `new -> scored` 自动推进成功
- [ ] 人工锁定后自动推进被阻止
- [ ] workbench `source` 过滤正确

### 11.2 插件测试

- [ ] 打开详情页后自动触发入库
- [ ] 不打开 side panel 也会入库
- [ ] 推荐列表页不会入库
- [ ] 快速切换候选人不会串 `candidate_id`
- [ ] 快速切换候选人不会串状态
- [ ] 打分完成后状态显示与当前候选人一致
- [ ] 状态保存成功后面板立即刷新

### 11.3 联调测试

- [ ] 打开候选人详情 1 秒内后端能查到此人
- [ ] 插件显示 `已入库`
- [ ] 打分完成后自动显示完整评分
- [ ] HR 改状态后 workbench 3 秒内可查到
- [ ] 后续重复打开同一人不会新建重复候选人

## 12. 联调顺序 Checklist

### 阶段 A：后端打底

- [ ] 完成 DB migration
- [ ] 完成 Repository
- [ ] 完成 `upsert` 接口
- [ ] 完成 `lookup` 接口
- [ ] 完成 `score` 回写接口

### 阶段 B：插件接入

- [ ] worker 自动入库联通
- [ ] side panel 展示入库状态
- [ ] side panel 保存状态联通
- [ ] 异步评分联通

### 阶段 C：后台联通

- [ ] workbench 增加 `source` 过滤
- [ ] workbench 展示插件候选人
- [ ] 详情页展示 timeline 和快照

## 13. 验收标准

- [ ] 进入候选人详情页后自动入库，不依赖手动点击
- [ ] side panel 未打开时也能入库
- [ ] 同一候选人同一 JD 不重复建档
- [ ] 插件中可修改并保存跟踪状态
- [ ] HR 后台可按来源和状态查询插件候选人
- [ ] 自动流程不会覆盖 HR 已手动设置的状态

## 14. 风险与注意事项

- `candidates.task_id` 当前为必填，插件候选人必须挂到插件专用 task，不能做成无 task 候选人。
- 推荐列表页与详情页必须继续严格区分，避免误入库。
- `source_candidate_key` 生成规则必须稳定，否则会造成重复建档。
- 截图继续走文件存储，不建议改成数据库 BLOB。
- 若后续要做“完整截图入库”，建议单独作为二期快照增强，不阻塞本期主流程。
