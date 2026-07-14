import { ImageResponse } from "next/og";

// This card is the same for every analysis (it intentionally reveals nothing
// private), so there's no reason to regenerate it per request. Dropping the edge
// runtime + a long CDN cache means each id's card is rendered at most once, then
// served from cache.
export const alt = "My Surge Analysis";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

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
          gap: 24,
          padding: "0 80px",
        }}
      >
        <div
          style={{
            width: 96,
            height: 96,
            borderRadius: 24,
            background: "#FF4D8D",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 54,
            fontWeight: 800,
            color: "#0A0A0B",
          }}
        >
          S
        </div>

        <div
          style={{
            fontSize: 60,
            fontWeight: 800,
            color: "#F5F5F6",
            letterSpacing: "-1px",
            lineHeight: 1,
          }}
        >
          My Surge Analysis
        </div>

        <div
          style={{
            fontSize: 30,
            color: "#9C9CA6",
            textAlign: "center",
            maxWidth: 800,
            lineHeight: 1.5,
          }}
        >
          I reviewed my video with Surge AI — hook, pacing, audio, and a
          focused next experiment.
        </div>

        <div
          style={{
            background: "#FF4D8D",
            border: "1px solid #FF4D8D",
            color: "#0A0A0B",
            fontSize: 24,
            fontWeight: 600,
            padding: "14px 36px",
            borderRadius: 100,
            marginTop: 8,
          }}
        >
          Review your video →
        </div>
      </div>
    ),
    {
      ...size,
      headers: {
        // Cache the rendered PNG at the CDN + browser; it never changes.
        "cache-control": "public, max-age=86400, s-maxage=604800, immutable",
      },
    }
  );
}
