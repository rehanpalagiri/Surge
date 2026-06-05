"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import UploadZone from "@/components/UploadZone";

const SHARE_CACHE = "surge-share-v1";
const SHARE_KEY = "/pending-share";
// Shared files older than 5 minutes are considered stale
const MAX_AGE_MS = 5 * 60 * 1000;

export default function SharePage() {
  const router = useRouter();
  const [sharedFile, setSharedFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty">("loading");

  useEffect(() => {
    async function retrieveSharedFile() {
      try {
        if (!("caches" in window)) {
          setStatus("empty");
          return;
        }

        const cache = await caches.open(SHARE_CACHE);
        const response = await cache.match(SHARE_KEY);

        if (!response) {
          setStatus("empty");
          return;
        }

        // Expire stale share entries (e.g. user navigated here directly)
        const ts = Number(response.headers.get("X-Timestamp") || 0);
        if (ts && Date.now() - ts > MAX_AGE_MS) {
          await cache.delete(SHARE_KEY);
          setStatus("empty");
          return;
        }

        const blob = await response.blob();
        const rawName = response.headers.get("X-File-Name") || "shared-video.mp4";
        const filename = decodeURIComponent(rawName);
        const file = new File([blob], filename, {
          type: blob.type || "video/mp4",
        });

        // Delete immediately so a page refresh doesn't re-show the same file
        await cache.delete(SHARE_KEY);

        setSharedFile(file);
        setStatus("ready");
      } catch (err) {
        console.error("[Surge] Failed to retrieve shared file:", err);
        setStatus("empty");
      }
    }

    retrieveSharedFile();
  }, []);

  // ── Loading ──────────────────────────────────────────────────────────────────
  if (status === "loading") {
    return (
      <main className="min-h-screen bg-background flex flex-col">
        <Nav />
        <div className="flex-1 flex items-center justify-center text-text-muted">
          Loading shared video…
        </div>
      </main>
    );
  }

  // ── No file (direct navigation or stale entry) ────────────────────────────────
  if (status === "empty") {
    return (
      <main className="min-h-screen bg-background flex flex-col">
        <Nav />
        <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6 text-center">
          <div className="text-5xl">🎬</div>
          <h1 className="text-xl font-bold text-text-primary">
            No video received
          </h1>
          <p className="text-text-muted text-sm max-w-xs leading-relaxed">
            Open TikTok or Instagram, find a video you saved, tap{" "}
            <span className="text-purple-to">···</span> → Share → Surge.
          </p>
          <button
            onClick={() => router.push("/")}
            className="gradient-btn text-white font-semibold px-6 py-3 rounded-xl mt-2"
          >
            Go to home
          </button>
        </div>
      </main>
    );
  }

  // ── File ready — show UploadZone pre-populated ────────────────────────────────
  return (
    <main className="min-h-screen bg-background flex flex-col">
      <Nav />
      <div className="flex-1 flex flex-col items-center px-4 py-8">
        <div className="w-full max-w-xl space-y-4">
          <div className="text-center space-y-1 mb-2">
            <div className="text-3xl">✅</div>
            <h1 className="text-xl font-bold text-text-primary">
              Video received!
            </h1>
            <p className="text-text-muted text-sm">
              Pick a niche and tap Analyze to get your score.
            </p>
          </div>
          <UploadZone initialFile={sharedFile} />
        </div>
      </div>
    </main>
  );
}
