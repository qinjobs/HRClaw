import "./index.css";
import { Composition } from "remotion";
import { PromoVideo, TOTAL_DURATION } from "./Composition";
import { video } from "./theme";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="HRClawPromo1080p"
        component={PromoVideo}
        durationInFrames={TOTAL_DURATION}
        fps={video.fps}
        width={video.width}
        height={video.height}
      />
    </>
  );
};
