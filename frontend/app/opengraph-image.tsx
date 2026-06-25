import { ImageResponse } from "next/og";

// No `runtime = "edge"`: edge runtime disables static generation, which forced
// this identical, input-less card to be re-rendered on every social-crawler
// request. On the default (Node) runtime Next prerenders it once at build, so
// it's served straight from the CDN and never regenerated per visitor.
export const alt = "Surge — AI-assisted video craft review";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "#0a0a0f",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 28,
          padding: "0 80px",
        }}
      >
        {/* Icon */}
        <div style={{ fontSize: 96 }}>🎬</div>

        {/* Wordmark */}
        <div
          style={{
            fontSize: 80,
            fontWeight: 800,
            color: "#a855f7",
            letterSpacing: "-2px",
            lineHeight: 1,
          }}
        >
          Surge
        </div>

        {/* Tagline */}
        <div
          style={{
            fontSize: 32,
            color: "#9ca3af",
            textAlign: "center",
            maxWidth: 780,
            lineHeight: 1.4,
          }}
        >
          Review your video craft before you post.
        </div>

        {/* Review pills */}
        <div
          style={{
            display: "flex",
            gap: 12,
            marginTop: 8,
          }}
        >
          {["Hook", "Pacing", "Audio", "Captions", "Experiment"].map((label) => (
            <div
              key={label}
              style={{
                background: "#1a1a2e",
                border: "1px solid #3b3b5c",
                color: "#c4b5fd",
                fontSize: 20,
                fontWeight: 600,
                padding: "10px 22px",
                borderRadius: 100,
              }}
            >
              {label}
            </div>
          ))}
        </div>

        {/* URL */}
        <div style={{ fontSize: 22, color: "#4b5563", marginTop: 8 }}>
          surge-chi-khaki.vercel.app
        </div>
      </div>
    ),
    { ...size }
  );
}
