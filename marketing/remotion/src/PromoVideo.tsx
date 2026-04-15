import {
  AbsoluteFill,
  Easing,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  Audio,
} from "remotion";
import type { CSSProperties, ReactNode } from "react";

import { brand } from "./theme";

type ClipSceneProps = {
  chapter: string;
  kicker: string;
  title: string;
  description: string;
  bullets: string[];
  src: string;
  durationInFrames: number;
  side?: "left" | "right";
  trimStart?: number;
  redactions?: Array<{
    x: number;
    y: number;
    width: number;
    height: number;
    borderRadius?: number;
  }>;
};

const fps = 30;

const SCENES = {
  intro: 90,
  login: 105,
  trial: 135,
  skill: 240,
  scorecard: 180,
  batchImport: 270,
  batchResults: 165,
  plugin: 210,
  outro: 105,
};

const STARTS = {
  intro: 0,
  login: SCENES.intro,
  trial: SCENES.intro + SCENES.login,
  skill: SCENES.intro + SCENES.login + SCENES.trial,
  scorecard: SCENES.intro + SCENES.login + SCENES.trial + SCENES.skill,
  batchImport:
    SCENES.intro + SCENES.login + SCENES.trial + SCENES.skill + SCENES.scorecard,
  batchResults:
    SCENES.intro +
    SCENES.login +
    SCENES.trial +
    SCENES.skill +
    SCENES.scorecard +
    SCENES.batchImport,
  plugin:
    SCENES.intro +
    SCENES.login +
    SCENES.trial +
    SCENES.skill +
    SCENES.scorecard +
    SCENES.batchImport +
    SCENES.batchResults,
  outro:
    SCENES.intro +
    SCENES.login +
    SCENES.trial +
    SCENES.skill +
    SCENES.scorecard +
    SCENES.batchImport +
    SCENES.batchResults +
    SCENES.plugin,
};

export const TOTAL_DURATION =
  SCENES.intro +
  SCENES.login +
  SCENES.trial +
  SCENES.skill +
  SCENES.scorecard +
  SCENES.batchImport +
  SCENES.batchResults +
  SCENES.plugin +
  SCENES.outro;

const fadeWindow = (frame: number, durationInFrames: number) =>
  interpolate(frame, [0, 10, durationInFrames - 18, durationInFrames], [0, 1, 1, 0], {
    easing: Easing.out(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const slideUp = (frame: number) =>
  interpolate(frame, [0, 24], [36, 0], {
    easing: Easing.out(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const panelBase: CSSProperties = {
  width: 620,
  padding: "36px 38px",
  borderRadius: 34,
  border: `1px solid ${brand.cardBorder}`,
  background: "linear-gradient(180deg, rgba(10,14,20,0.8), rgba(7,10,15,0.64))",
  backdropFilter: "blur(22px)",
  boxShadow: brand.shadow,
};

const pillStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 10,
  padding: "10px 16px",
  borderRadius: 999,
  border: `1px solid ${brand.cardBorder}`,
  background: "rgba(255,255,255,0.06)",
  color: brand.text,
  fontSize: 24,
  fontWeight: 500,
  letterSpacing: "-0.02em",
};

const featureColor = (text: string) => {
  if (text.includes("JD")) return brand.blue;
  if (text.includes("批量")) return brand.green;
  if (text.includes("浏览器")) return brand.orange;
  return "#d0d7e2";
};

const mosaicBase = (
  width: number,
  height: number,
  borderRadius: number,
): CSSProperties => ({
  position: "absolute",
  left: 0,
  top: 0,
  width,
  height,
  borderRadius,
  overflow: "hidden",
  background:
    "linear-gradient(135deg, rgba(17,24,39,0.92), rgba(55,65,81,0.88))",
  border: "1px solid rgba(255,255,255,0.22)",
  boxShadow: "0 16px 40px rgba(0,0,0,0.25)",
});

const MosaicPatch: React.FC<{
  x: number;
  y: number;
  width: number;
  height: number;
  borderRadius?: number;
}> = ({ x, y, width, height, borderRadius = 18 }) => {
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width,
        height,
      }}
    >
      <div style={mosaicBase(width, height, borderRadius)} />
      <div
        style={{
          ...mosaicBase(width, height, borderRadius),
          backgroundImage: `
            linear-gradient(90deg, rgba(255,255,255,0.10) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.10) 50%, rgba(255,255,255,0.10) 75%, transparent 75%, transparent 100%),
            linear-gradient(0deg, rgba(255,255,255,0.08) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.08) 75%, transparent 75%, transparent 100%)
          `,
          backgroundSize: "18px 18px, 18px 18px",
          mixBlendMode: "screen",
          opacity: 0.78,
        }}
      />
      <div
        style={{
          ...mosaicBase(width, height, borderRadius),
          background:
            "linear-gradient(180deg, rgba(255,255,255,0.16), rgba(255,255,255,0.03))",
          backdropFilter: "blur(20px) saturate(0.75)",
        }}
      />
    </div>
  );
};

const Backplate: React.FC<{ children?: ReactNode }> = ({ children }) => {
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(circle at top left, rgba(10,132,255,0.16), transparent 42%), radial-gradient(circle at bottom right, rgba(48,209,88,0.12), transparent 34%), ${brand.bg}`,
        fontFamily: brand.font,
        color: brand.text,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

const ClipScene: React.FC<ClipSceneProps> = ({
  chapter,
  kicker,
  title,
  description,
  bullets,
  src,
  durationInFrames,
  side = "left",
  trimStart = 0,
  redactions = [],
}) => {
  const frame = useCurrentFrame();
  const panelOpacity = fadeWindow(frame, durationInFrames);
  const panelTranslate = slideUp(frame);
  const titleOpacity = interpolate(frame, [6, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyOpacity = interpolate(frame, [16, 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const progress = interpolate(frame, [10, durationInFrames - 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const isLeft = side === "left";
  const align = isLeft ? "flex-start" : "flex-end";

  return (
    <Backplate>
      <OffthreadVideo
        src={staticFile(src)}
        startFrom={trimStart}
        endAt={trimStart + durationInFrames}
        muted
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          filter: "saturate(1.06) contrast(1.02)",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(5,7,11,0.10) 0%, rgba(5,7,11,0.38) 38%, rgba(5,7,11,0.72) 100%)",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            isLeft
              ? "linear-gradient(90deg, rgba(5,7,11,0.78) 0%, rgba(5,7,11,0.48) 35%, rgba(5,7,11,0.18) 65%, rgba(5,7,11,0.06) 100%)"
              : "linear-gradient(270deg, rgba(5,7,11,0.78) 0%, rgba(5,7,11,0.48) 35%, rgba(5,7,11,0.18) 65%, rgba(5,7,11,0.06) 100%)",
        }}
      />
      {redactions.map((redaction, index) => (
        <MosaicPatch key={`${redaction.x}-${redaction.y}-${index}`} {...redaction} />
      ))}
      <div
        style={{
          position: "absolute",
          inset: 72,
          display: "flex",
          alignItems: "flex-end",
          justifyContent: align,
        }}
      >
        <div
          style={{
            ...panelBase,
            opacity: panelOpacity,
            transform: `translateY(${panelTranslate}px)`,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 16,
              marginBottom: 18,
            }}
          >
            <div
              style={{
                fontSize: 18,
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: "rgba(245,247,251,0.56)",
              }}
            >
              {kicker}
            </div>
            <div
              style={{
                padding: "8px 14px",
                borderRadius: 999,
                border: `1px solid ${brand.cardBorder}`,
                background: "rgba(255,255,255,0.05)",
                color: "rgba(245,247,251,0.72)",
                fontSize: 16,
                fontWeight: 600,
                letterSpacing: "0.08em",
              }}
            >
              {chapter}
            </div>
          </div>
          <div
            style={{
              opacity: titleOpacity,
              fontSize: 64,
              lineHeight: 1.02,
              fontWeight: 700,
              letterSpacing: "-0.05em",
              marginBottom: 18,
            }}
          >
            {title}
          </div>
          <div
            style={{
              opacity: bodyOpacity,
              fontSize: 28,
              lineHeight: 1.55,
              color: brand.textSoft,
              letterSpacing: "-0.025em",
            }}
          >
            {description}
          </div>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 12,
              marginTop: 28,
            }}
          >
            {bullets.map((bullet, index) => (
              <div
                key={bullet}
                style={{
                  ...pillStyle,
                  opacity: interpolate(frame, [26 + index * 7, 38 + index * 7], [0, 1], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  }),
                  transform: `translateY(${interpolate(
                    frame,
                    [26 + index * 7, 38 + index * 7],
                    [12, 0],
                    {
                      extrapolateLeft: "clamp",
                      extrapolateRight: "clamp",
                    },
                  )}px)`,
                }}
              >
                <div
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 999,
                    background: featureColor(bullet),
                    boxShadow: `0 0 16px ${featureColor(bullet)}`,
                  }}
                />
                <span>{bullet}</span>
              </div>
            ))}
          </div>
          <div
            style={{
              marginTop: 28,
              height: 6,
              width: "100%",
              borderRadius: 999,
              overflow: "hidden",
              background: "rgba(255,255,255,0.08)",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${progress * 100}%`,
                borderRadius: 999,
                background:
                  "linear-gradient(90deg, rgba(10,132,255,0.95), rgba(48,209,88,0.95))",
                boxShadow: "0 0 18px rgba(10,132,255,0.35)",
              }}
            />
          </div>
        </div>
      </div>
    </Backplate>
  );
};

const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const splashDuration = 30; // first 30 frames show slogan splash
  const introFrame = Math.max(0, frame - splashDuration);
  const enter = spring({
    fps,
    frame: introFrame,
    config: {
      damping: 16,
      stiffness: 120,
      mass: 0.9,
    },
  });

  const showSplash = frame < splashDuration;

  return (
    <Backplate>
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          padding: 80,
        }}
      >
        {showSplash ? (
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              right: 0,
              bottom: 0,
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              background: "#ffffff",
            }}
          >
            <Img
              src={staticFile("HRClaw-slogan.png")}
              style={{
                width: "80%",
                height: "auto",
                objectFit: "contain",
              }}
            />
          </div>
        ) : (
          <>
            <Img
              src={staticFile("MVP.png")}
              style={{
                position: "absolute",
                right: -120,
                top: -60,
                width: width * 0.62,
                opacity: 0.14,
                filter: "blur(2px)",
                transform: `scale(${0.92 + enter * 0.08}) rotate(-6deg)`,
              }}
            />
            <div
              style={{
                ...panelBase,
                width: 1160,
                padding: "54px 64px",
                textAlign: "center",
                transform: `scale(${0.92 + enter * 0.08})`,
                opacity: interpolate(introFrame, [0, 10, 70, 90], [0, 1, 1, 0], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                }),
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 22,
                  marginBottom: 28,
                }}
              >
                <Img
                  src={staticFile("logo.jpg")}
                  style={{
                    width: 120,
                    borderRadius: 26,
                    boxShadow: "0 18px 40px rgba(0,0,0,0.22)",
                  }}
                />
                <div
                  style={{
                    padding: "10px 18px",
                    borderRadius: 999,
                    background: brand.blueSoft,
                    color: "#dcecff",
                    fontSize: 22,
                    fontWeight: 600,
                    letterSpacing: "-0.02em",
                  }}
                >
                  Local-first recruiting copilot
                </div>
              </div>
              <div
                style={{
                  fontSize: 118,
                  lineHeight: 0.95,
                  fontWeight: 760,
                  letterSpacing: "-0.08em",
                  marginBottom: 24,
                }}
              >
                HRClaw
              </div>
              <div
                style={{
                  fontSize: 38,
                  lineHeight: 1.45,
                  color: brand.textSoft,
                  letterSpacing: "-0.03em",
                  maxWidth: 920,
                  margin: "0 auto",
                }}
              >
                把 JD、PDF 简历、浏览器候选人页面，
                <br />
                变成招聘团队能直接执行的筛选结论。
              </div>
            </div>
          </>
        )}
      </AbsoluteFill>
    </Backplate>
  );
};

const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = fadeWindow(frame, SCENES.outro);
  const shift = slideUp(frame);

  return (
    <Backplate>
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          padding: 80,
        }}
      >
        <div
          style={{
            ...panelBase,
            width: 1220,
            padding: "54px 64px",
            opacity,
            transform: `translateY(${shift}px)`,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 20,
              marginBottom: 26,
            }}
          >
            <Img
              src={staticFile("logo.jpg")}
              style={{
                width: 92,
                borderRadius: 24,
              }}
            />
            <div>
              <div
                style={{
                  fontSize: 62,
                  fontWeight: 760,
                  letterSpacing: "-0.06em",
                  lineHeight: 1,
                }}
              >
                HRClaw
              </div>
              <div
                style={{
                  fontSize: 24,
                  color: brand.textSoft,
                  marginTop: 6,
                  letterSpacing: "-0.02em",
                }}
              >
                Recruiter-ready decisions, not another generic ATS demo.
              </div>
            </div>
          </div>
          <div
            style={{
              display: "flex",
              gap: 16,
              flexWrap: "wrap",
              marginBottom: 30,
            }}
          >
            {["JD → scorecard", "Resume → score", "Browser page → same scoring engine"].map((item) => (
              <div key={item} style={pillStyle}>
                {item}
              </div>
            ))}
          </div>
          <div
            style={{
              fontSize: 30,
              lineHeight: 1.6,
              color: brand.textSoft,
              letterSpacing: "-0.025em",
            }}
          >
            GitHub: qinjobs/HRClaw
            <br />
            Contact: hrclaw@126.com
          </div>
        </div>
      </AbsoluteFill>
    </Backplate>
  );
};

export const PromoVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const musicVolume = interpolate(
    frame,
    [0, 30, TOTAL_DURATION - 60, TOTAL_DURATION],
    [0, 0.65, 0.65, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  return (
    <AbsoluteFill style={{ backgroundColor: brand.bg }}>
      {/* 背景音乐：将音乐文件放到 public/bg-music.mp3 */}
      <Audio src={staticFile("bg-music.mp3")} volume={musicVolume} />
      <Sequence from={STARTS.intro} durationInFrames={SCENES.intro}>
        <Intro />
      </Sequence>

      <Sequence from={STARTS.login} durationInFrames={SCENES.login}>
        <ClipScene
          chapter="01 / 07"
          kicker="Problem"
          title="招聘初筛太碎"
          description="登录、切页、找人、同步状态，HR 的时间很容易花在重复动作上。"
          bullets={["登录后台", "切换页面", "重复操作"]}
          src="01-login.mp4"
          durationInFrames={SCENES.login}
          side="left"
          trimStart={75}
        />
      </Sequence>

      <Sequence from={STARTS.trial} durationInFrames={SCENES.trial}>
        <ClipScene
          chapter="02 / 07"
          kicker="Trial Hub"
          title="试点中心把流程收口"
          description="一个岗位、一位 HR、一条评分引擎。试点要用的入口，都收在同一页。"
          bullets={["统一入口", "本地优先", "试点工作流"]}
          src="02-trial.mp4"
          durationInFrames={SCENES.trial}
          side="right"
          trimStart={30}
        />
      </Sequence>

      <Sequence from={STARTS.skill} durationInFrames={SCENES.skill}>
        <ClipScene
          chapter="03 / 07"
          kicker="Skill"
          title="Skill 先把标准写清楚"
          description="jd-scorecard 把 JD 变成评分卡，也能按评分卡给简历打分，再渲染成飞书 / 钉钉结果。"
          bullets={["JD → Scorecard", "Resume → Score", "Chat-ready"]}
          src="07-hrclaw-skill.mp4"
          durationInFrames={SCENES.skill}
          side="right"
          trimStart={60}
        />
      </Sequence>

      <Sequence from={STARTS.scorecard} durationInFrames={SCENES.scorecard}>
        <ClipScene
          chapter="04 / 07"
          kicker="Scorecard"
          title="筛选口径先统一"
          description="必备项、加分项、红旗、阈值和面试题，都从同一份岗位标准出发。"
          bullets={["Must-have", "Red flags", "Interview questions"]}
          src="03-scorecard.mp4"
          durationInFrames={SCENES.scorecard}
          side="right"
          trimStart={150}
        />
      </Sequence>

      <Sequence from={STARTS.batchImport} durationInFrames={SCENES.batchImport}>
        <ClipScene
          chapter="05 / 07"
          kicker="Batch Import"
          title="批量简历，直接出结论"
          description="导入 PDF / DOC / DOCX，自动解析、打分、形成批次结果。高频岗位尤其省时间。"
          bullets={["Batch import", "Auto parse", "Recommend / Review / Reject"]}
          src="04-batch-import.mp4"
          durationInFrames={SCENES.batchImport}
          side="left"
          trimStart={120}
        />
      </Sequence>

      <Sequence from={STARTS.batchResults} durationInFrames={SCENES.batchResults}>
        <ClipScene
          chapter="06 / 07"
          kicker="Results"
          title="每个分数都有证据"
          description="不只是一个总分，还给命中项、缺失项和下一步建议，方便 HR 和用人经理一起复核。"
          bullets={["命中项", "缺失项", "下一步建议"]}
          src="05-batch-results.mp4"
          durationInFrames={SCENES.batchResults}
          side="right"
          trimStart={30}
        />
      </Sequence>

      <Sequence from={STARTS.plugin} durationInFrames={SCENES.plugin}>
        <ClipScene
          chapter="07 / 07"
          kicker="Browser Capture"
          title="浏览器里也能继续工作"
          description="侧边栏采集当前候选人页面，走同一套评分后端，再同步回工作台。"
          bullets={["Chrome side panel", "Candidate capture", "Same scoring engine"]}
          src="06-plugin-sidepanel.mp4"
          durationInFrames={SCENES.plugin}
          side="left"
          trimStart={150}
          redactions={[
            { x: 114, y: 36, width: 92, height: 106, borderRadius: 30 },
            { x: 232, y: 32, width: 258, height: 66, borderRadius: 24 },
          ]}
        />
      </Sequence>

      <Sequence from={STARTS.outro} durationInFrames={SCENES.outro}>
        <Outro />
      </Sequence>
    </AbsoluteFill>
  );
};
