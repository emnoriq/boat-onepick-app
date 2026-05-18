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
          background: "linear-gradient(135deg, #FF6B6B 0%, #FF8E53 50%, #FFBE0B 100%)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 4,
        }}
      >
        <div style={{ fontSize: 90, lineHeight: 1 }}>⛵</div>
        <div
          style={{
            fontSize: 22,
            fontWeight: 900,
            color: "white",
            letterSpacing: -1,
            textShadow: "0 1px 4px rgba(0,0,0,0.2)",
          }}
        >
          三連複1点
        </div>
      </div>
    ),
    { ...size }
  );
}
