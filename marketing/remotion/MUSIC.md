# 背景音乐指南（为成片配“高大上”音乐）

## 放置位置
将最终的音乐文件命名为 `bg-music.mp3`（或 `bg-music.m4a` 等 Remotion 支持的音频格式），并放到：

- marketing/remotion/public/bg-music.mp3

Remotion 的 `staticFile("bg-music.mp3")` 会自动引用该文件。

## 音量与淡入淡出
项目已在 `src/PromoVideo.tsx` 中集成音乐轨，默认实现：
- 片头 30 帧淡入，片尾 60 帧淡出
- 峰值音量约 0.85（可在源码中调整）

如果想微调，请编辑 `src/PromoVideo.tsx` 中的 `musicVolume` 插值区间。

## 曲风建议（“高大上”）
- 史诗管弦（Epic orchestral / cinematic） — 用于营造史诗感与可信度
- 现代合成器加弦乐（Modern synth + strings） — 专业且有科技感
- 轻快大气（Uplifting corporate） — 温暖且易被企业场景接受

## 推荐来源（商业用途请注意授权）
- YouTube Audio Library（免费，筛选可商用曲目）
- Free Music Archive（部分曲目允许商用）
- Bensound（部分曲目免费，商业请查看授权）
- Artlist / Epidemic Sound（付费订阅，曲目质量与授权友好）

## 如何替换/测试
1. 拷贝或下载合适曲目到 `marketing/remotion/public/bg-music.mp3`。
2. 在项目目录运行：

```bash
cd marketing/remotion
npm run dev   # 预览 Remotion Studio
# 或渲染成片
npm run render
```

## 许可注意事项
- 商用宣传片请务必检查音频授权（是否允许商业使用、是否需署名等）。
- 若需要，我可以根据你的授权偏好（完全免费 / 允许署名 / 付费）推荐具体曲目。

---
如果你要我直接帮你挑一首（我可以列出 3 个候选曲目并说明授权），请告诉我你偏向“史诗管弦 / 现代科技 / 轻快大气” 中的哪一类，或把你已有的音乐文件上传到 `marketing/remotion/public/`。