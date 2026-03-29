<p align="center">
  <img src="assets/logo.jpg" alt="HRClaw logo" width="220" />
</p>

# HRClaw JD 评分卡 Skill

<p align="center">把 JD 和 PDF 简历变成可执行的招聘结论。</p>
<p align="center">给招聘团队一个能直接用的初筛标准、简历打分和聊天版结果。</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License" />
  <img src="https://img.shields.io/badge/Skill-JD%20Scorecard-blue.svg" alt="JD Scorecard Skill" />
  <img src="https://img.shields.io/badge/Focus-Recruiting%20Ops-red.svg" alt="Recruiting Ops" />
</p>

<p align="center">
  <a href="mailto:hrclaw@126.com">联系邮箱：hrclaw@126.com</a> ·
  <a href="README.md">英文首页</a> ·
  打开 Issues：`中文 demo 预约` / `Demo request`
</p>

![中文 demo](assets/demo-zh.gif)

> 这套 skill 的目标很简单：把 JD 变成评分卡，把 PDF 简历变成可追踪的打分结果，再把结果整理成招聘群里一眼能读懂的格式。

## 适合场景

- 招聘量大、需要快速初筛的团队
- 想统一筛选标准、减少主观判断的团队
- 飞书 / 钉钉使用频繁的招聘协作场景
- HR、用人经理、产品一起协作的流程

## 这套 Skill 能做什么

- `JD -> 评分卡`
- `PDF 简历 -> 按评分卡打分`
- `JSON -> 方便程序继续处理`
- `Markdown -> 方便 HR / 用人经理查看`
- `飞书 / 钉钉版 -> 方便群聊直接转发`

## 输出形式

| 形式 | 适合谁 | 对应文件 |
| --- | --- | --- |
| 纯 JSON | 接系统、做自动化 | `skills/jd-scorecard/templates/scorecard.json` |
| 普通 Markdown | HR、招聘负责人、用人经理 | `skills/jd-scorecard/templates/scorecard.md` |
| 聊天版 Markdown | 飞书、钉钉、Teams、Slack | `skills/jd-scorecard/templates/chat-scorecard.md` |

## 你可以直接这样用

```text
把这段 JD 转成招聘评分卡，输出纯 JSON
用这份 PDF 简历按下面评分卡打分，输出纯 JSON
用飞书版输出这份评分卡
```

如果是 PDF 简历，建议同时给出评分卡或者 JD。
如果 PDF 没有文本层，系统会标记成 `needs_ocr`，不会乱猜。

## 你会得到什么

- 清晰的硬筛条件
- 必备项和加分项
- 可直接问人的面试题
- 可快速拒人的红旗信号
- 带证据的简历分数、命中项和下一步建议
- 适合飞书 / 钉钉群聊转发的结果格式

## 本地安装

如果你在本地用 Codex，可以先把 skill 目录放到技能目录里：

```bash
cp -R skills/jd-scorecard ~/.codex/skills/
```

然后重启 Codex，就能直接调用这个 skill。

## 公开版 vs 私有版

| 公开 skill | 私有产品 |
| --- | --- |
| JD 评分 | BOSS 集成 |
| 简历打分 | 团队校准 |
| 聊天版输出 | 工作流自动化 |
| 示例和模板 | 内网部署与支持 |

公开版只做文本、模板和评分逻辑，方便传播和复用。
私有版再补 BOSS 相关流程、团队协作和更深的招聘工作流。

## 仓库导航

- [Skill 定义](skills/jd-scorecard/SKILL.md)
- [JD 提示词](skills/jd-scorecard/prompts/jd-to-scorecard.md)
- [简历打分提示词](skills/jd-scorecard/prompts/resume-score.md)
- [技能包参考](skills/jd-scorecard/references/)
- [飞书/钉钉版评分卡模板](skills/jd-scorecard/templates/chat-scorecard.md)
- [飞书/钉钉版简历打分模板](skills/jd-scorecard/templates/chat-resume-score.md)
- [示例目录](skills/jd-scorecard/examples/)
- [校验工作流](.github/workflows/validate-skill.yml)

## 技能包参考

- [英文首页](README.md)
- [中文说明书-部署与使用](docs/中文说明书-部署与使用.md)
- [内网部署实施清单](docs/内网部署实施清单.md)
- [CLAWHUB 发布检查清单](CLAWHUB_PUBLISH_CHECKLIST.md)
- [快速上手](skills/jd-scorecard/references/quickstart.md)
- [FAQ](skills/jd-scorecard/references/faq.md)
- [限制说明](skills/jd-scorecard/references/limitations.md)

## 联系方式

- 邮箱：[hrclaw@126.com](mailto:hrclaw@126.com)
- GitHub Issues：打开 Issues 页签，选择 `中文 demo 预约` 或 `Demo request`

## 许可证

MIT
