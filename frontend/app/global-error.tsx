"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "0 16px",
          textAlign: "center",
          background: "#0B0D0B",
          color: "#F2EFE9",
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        }}
      >
        <div
          style={{
            fontWeight: 800,
            fontSize: 20,
            color: "#F2EFE9",
            letterSpacing: "-0.02em",
            marginBottom: 48,
          }}
        >
          Surge
        </div>

        <h1
          style={{
            marginTop: 16,
            fontSize: 28,
            fontWeight: 800,
            color: "#F2EFE9",
            letterSpacing: "-0.02em",
          }}
        >
          Something went wrong
        </h1>
        <p
          style={{
            marginTop: 12,
            color: "#A29B91",
            maxWidth: 384,
          }}
        >
          An unexpected error occurred. You can try again or head back home.
        </p>

        <div style={{ marginTop: 32, display: "flex", alignItems: "center", gap: 16 }}>
          <button
            onClick={() => reset()}
            style={{
              background: "#C7F36B",
              color: "#0B0D0B",
              fontWeight: 600,
              padding: "12px 24px",
              borderRadius: 16,
              border: "none",
              cursor: "pointer",
              fontSize: 16,
            }}
          >
            Try again
          </button>
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- global-error replaces the root layout, so the Link/router context may be unavailable */}
          <a
            href="/"
            style={{
              color: "#A29B91",
              fontWeight: 600,
              padding: "12px 24px",
              borderRadius: 16,
              textDecoration: "none",
              fontSize: 16,
            }}
          >
            Back to home
          </a>
        </div>
      </body>
    </html>
  );
}
