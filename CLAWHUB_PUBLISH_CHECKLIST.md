# CLAWHUB 发布检查清单

> 目标：把 `skills/jd-scorecard/` 作为独立 skill 包发布到 CLAWHUB，而不是把整个 HRClaw 仓库一起打包。

## 1. 发布范围

- [ ] 只发布 `skills/jd-scorecard/` 目录
- [ ] 不把 `admin_frontend/`、`src/`、`release/`、`install/`、`tests/` 一起带入 skill 包
- [ ] 根目录的 `README.md`、`README.zh-CN.md`、`docs/` 保留给仓库级说明，不混入 skill 包

## 2. Skill 包结构

- [ ] `skills/jd-scorecard/SKILL.md` 存在
- [ ] `SKILL.md` front matter 只保留 `name` 和 `description`
- [ ] `description` 同时覆盖两条主流程：
  - [ ] `JD -> scorecard`
  - [ ] `Resume PDF/text -> score against a scorecard`
- [ ] `agents/openai.yaml` 存在且与 `SKILL.md` 一致
- [ ] `prompts/` 只放技能运行时需要的提示词
- [ ] `templates/` 只放输出模板
- [ ] `examples/` 只放可公开的示例数据
- [ ] `assets/` 只放图标、logo、demo 动图等静态资源
- [ ] `references/` 只放简短的使用参考，不塞仓库级部署文档

## 3. 必要文件

- [ ] `skills/jd-scorecard/prompts/jd-to-scorecard.md`
- [ ] `skills/jd-scorecard/prompts/resume-score.md`
- [ ] `skills/jd-scorecard/prompts/interview-questions.md`
- [ ] `skills/jd-scorecard/templates/scorecard.json`
- [ ] `skills/jd-scorecard/templates/scorecard.md`
- [ ] `skills/jd-scorecard/templates/chat-scorecard.md`
- [ ] `skills/jd-scorecard/templates/resume-score.json`
- [ ] `skills/jd-scorecard/templates/resume-score.md`
- [ ] `skills/jd-scorecard/templates/chat-resume-score.md`
- [ ] `skills/jd-scorecard/references/quickstart.md`
- [ ] `skills/jd-scorecard/references/faq.md`
- [ ] `skills/jd-scorecard/references/limitations.md`

## 4. 公开内容边界

- [ ] 不包含 BOSS 登录态、cookie、session、token
- [ ] 不包含私有候选人数据
- [ ] 不包含内网部署材料
- [ ] 不包含只能给客户看的定制评分规则
- [ ] 不把 `docs/中文说明书-部署与使用.md`、`docs/内网部署实施清单.md` 拷贝进 skill 包

## 5. 可展示性

- [ ] `icon_small` 在列表里看得清
- [ ] `icon_large` 在详情页里识别度高
- [ ] `demo.gif` / `demo-zh.gif` 正常可见
- [ ] README 首屏能一句话讲清楚用途
- [ ] README 里有 `Feishu / DingTalk` 聊天版说明
- [ ] README 里有明确联系入口

## 6. 运行校验

- [ ] `skills/jd-scorecard/SKILL.md` 能被技能加载
- [ ] 纯 JSON 输出可解析
- [ ] 简历打分输出可解析
- [ ] 扫描版 PDF 会返回 `needs_ocr`
- [ ] 聊天版输出适合直接贴进飞书/钉钉

## 7. 仓库级校验

- [ ] `README.md` 链接不指向已删除文件
- [ ] `README.zh-CN.md` 链接不指向已删除文件
- [ ] `validate-skill.yml` 覆盖所有必须文件
- [ ] 没有 `.DS_Store`、临时文件、空目录污染
- [ ] `git status` 干净

## 8. CLAWHUB 发布页

- [ ] `display_name` 清晰
- [ ] `short_description` 同时表达 JD 评分和简历打分
- [ ] `default_prompt` 能覆盖三种常见请求：
  - [ ] JD 生成评分卡
  - [ ] PDF 简历打分
  - [ ] 飞书/钉钉聊天版输出
- [ ] icon 和品牌色一致
- [ ] 页面上没有断链或空白模块

## 9. 发布后回查

- [ ] 用一个真实 JD 做 smoke test
- [ ] 用一份真实 PDF 简历做 smoke test
- [ ] 检查结果是不是纯 JSON 或聊天版 markdown
- [ ] 看前 5 个真实用户是否会卡在安装、上传或理解输出
- [ ] 根据真实使用情况调整阈值和示例

## 10. 不要做的事

- [ ] 不要把整个 HRClaw 仓库当成 skill 包发布
- [ ] 不要把内部说明书、安装脚本、前后端代码一起塞进 CLAWHUB
- [ ] 不要为了发布而扩大 skill 范围
- [ ] 不要在技能包里留下和当前行为无关的长文档
