import { ImageResponse } from "next/og";

// No `runtime = "edge"`: edge runtime disables static generation, which forced
// this identical, input-less card to be re-rendered on every social-crawler
// request. On the default (Node) runtime Next prerenders it once at build, so
// it's served straight from the CDN and never regenerated per visitor.
export const alt = "Surge — AI-assisted retention craft review";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

import { SITE_HOST } from "@/lib/site";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "#0A0A0B",
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
            background: "#FF4D8D",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              fontSize: 68,
              fontWeight: 800,
              color: "#0A0A0B",
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
            color: "#F5F5F6",
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
            color: "#9C9CA6",
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
                background: "#18181B",
                border: "1px solid #29292F",
                color: "#FF4D8D",
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
        <div style={{ fontSize: 22, color: "#9C9CA6", marginTop: 8 }}>
          {SITE_HOST}
        </div>
      </div>
    ),
    { ...size }
  );
}
