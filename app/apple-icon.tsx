import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: 180,
          height: 180,
          borderRadius: 40,
          background:
            "radial-gradient(ellipse at 48% 38%, #FF7043 0%, #D84315 38%, #4A0E05 80%, #1A0402 100%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
          position: "relative",
        }}
      >
        {/* 光の反射（上部ハイライト） */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: 80,
            background:
              "radial-gradient(ellipse at 50% 0%, rgba(255,255,255,0.18) 0%, transparent 70%)",
            borderRadius: "40px 40px 0 0",
          }}
        />

        {/* ボートSVG */}
        <svg
          width="130"
          height="108"
          viewBox="0 0 130 108"
          xmlns="http://www.w3.org/2000/svg"
        >
          {/* セール（帆） */}
          <path
            d="M 62 8 L 62 66 L 108 58 Z"
            fill="white"
            opacity="0.95"
          />
          {/* マスト */}
          <rect x="58" y="6" width="7" height="64" rx="3.5" fill="white" />
          {/* 船体（ハル） */}
          <path
            d="M 16 70 L 114 70 Q 112 86 65 90 Q 18 86 16 70 Z"
            fill="white"
          />
          {/* 波1 */}
          <path
            d="M 4 96 Q 18 89 32 96 Q 46 103 60 96 Q 74 89 88 96 Q 102 103 116 96 Q 124 92 130 95"
            stroke="rgba(255,255,255,0.45)"
            strokeWidth="3.5"
            fill="none"
            strokeLinecap="round"
          />
          {/* 波2（小さく） */}
          <path
            d="M 10 104 Q 22 99 34 104 Q 46 109 58 104 Q 70 99 82 104"
            stroke="rgba(255,255,255,0.25)"
            strokeWidth="2.5"
            fill="none"
            strokeLinecap="round"
          />
        </svg>
      </div>
    ),
    { ...size }
  );
}
