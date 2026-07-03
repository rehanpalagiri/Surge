import { ImageResponse } from "next/og";

// No `runtime = "edge"`: edge runtime disables static generation, which forced
// this identical, input-less card to be re-rendered on every social-crawler
// request. On the default (Node) runtime Next prerenders it once at build, so
// it's served straight from the CDN and never regenerated per visitor.
export const alt = "Surge — AI-assisted retention craft review";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://surge-chi-khaki.vercel.app";
const SITE_HOST = new URL(SITE_URL).host;

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "#121014",
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
        <div
          style={{
            width: 120,
            height: 120,
            borderRadius: 28,
            background: "#F5A623",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              fontSize: 68,
              fontWeight: 800,
              color: "#121014",
              lineHeight: 1,
            }}
          >
            S
          </div>
        </div>

        {/* Wordmark */}
        <div
          style={{
            fontSize: 80,
            fontWeight: 800,
            color: "#F2EFE9",
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
            color: "#A29B91",
            textAlign: "center",
            maxWidth: 780,
            lineHeight: 1.4,
          }}
        >
          Find attention risks before you post.
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
                background: "#1E1B21",
                border: "1px solid #2E2A31",
                color: "#F5A623",
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
        <div style={{ fontSize: 22, color: "#A29B91", marginTop: 8 }}>
          {SITE_HOST}
        </div>
      </div>
    ),
    { ...size }
  );
}
