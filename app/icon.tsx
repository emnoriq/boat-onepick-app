import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 7,
          background:
            "radial-gradient(ellipse at 45% 35%, #FF7043 0%, #D84315 45%, #1A0402 100%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
        }}
      >
        <svg width="22" height="18" viewBox="0 0 22 18" xmlns="http://www.w3.org/2000/svg">
          {/* セール */}
          <path d="M 10 1 L 10 11 L 19 9.5 Z" fill="white" opacity="0.95" />
          {/* マスト */}
          <rect x="9" y="0.5" width="2" height="11.5" rx="1" fill="white" />
          {/* 船体 */}
          <path d="M 2 12 L 20 12 Q 19.5 15.5 11 16.5 Q 2.5 15.5 2 12 Z" fill="white" />
        </svg>
      </div>
    ),
    { ...size }
  );
}
