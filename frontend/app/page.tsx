"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import UploadZone from "@/components/UploadZone";
import Nav from "@/components/Nav";
import { getToken } from "@/lib/auth";

type Platform = "tiktok" | "instagram";

const PLATFORM_LABEL: Record<Platform, string> = {
  tiktok: "TikTok",
  instagram: "Instagram",
};

// ─── Splash screen ────────────────────────────────────────────────────────────

function SplashScreen({ onGuest, deleted }: { onGuest: () => void; deleted: boolean }) {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 bg-zinc-950">
      {deleted && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-sm px-5 py-3 rounded-xl shadow-lg">
          Your account has been deleted.
        </div>
      )}
      <div className="w-full max-w-md text-center space-y-10">
        {/* Branding */}
        <div className="space-y-4">
          <div className="text-6xl">🎬</div>
          <h1 className="text-5xl font-extrabold text-purple-500 tracking-tight">
            Surge
          </h1>
          <p className="text-zinc-400 text-lg leading-relaxed max-w-sm mx-auto">
            Find out if your video will go viral — before you post it.
          </p>
        </div>

        {/* Feature chips */}
        <div className="flex flex-wrap justify-center gap-2">
          {[
            "6-score AI breakdown",
            "Hook analysis",
            "Caption rewrites",
            "Full improvement plan",
            "TikTok & Instagram",
          ].map((f) => (
            <span
              key={f}
              className="bg-zinc-900 border border-zinc-700 text-zinc-400 text-xs px-3 py-1.5 rounded-full"
            >
              {f}
            </span>
          ))}
        </div>

        {/* CTAs */}
        <div className="space-y-3">
          <Link
            href="/signup"
            className="block w-full bg-purple-600 hover:bg-purple-500 text-white font-bold py-4 rounded-xl text-lg transition-all hover:shadow-[0_0_15px_rgba(168,85,247,0.5)] active:scale-[0.98]"
          >
            Create free account
          </Link>

          <Link
            href="/login"
            className="block w-full bg-zinc-900 border border-zinc-700 text-white font-semibold py-3 rounded-xl hover:border-purple-500/50 transition-colors"
          >
            Log in
          </Link>

          <div className="pt-2">
            <button
              onClick={onGuest}
              className="text-zinc-500 text-sm hover:text-zinc-300 transition-colors"
            >
              Continue as guest
            </button>
            <p className="text-zinc-600 text-xs mt-1">
              Results are locked · no history saved
            </p>
          </div>

          <p className="text-zinc-600 text-xs pt-1">
            Not sure what you&apos;ll get?{" "}
            <Link href="/sample" className="hover:text-zinc-400 underline transition-colors">
              See a sample report →
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Home() {
  const [platform, setPlatform] = useState<Platform>("tiktok");
  const [showSplash, setShowSplash] = useState<boolean | null>(null);
  const [deleted, setDeleted] = useState(false);

  useEffect(() => {
    const token = getToken();
    setShowSplash(!token);
    const params = new URLSearchParams(window.location.search);
    if (params.get("deleted") === "1") {
      setDeleted(true);
      window.history.replaceState({}, "", "/");
    }
  }, []);

  if (showSplash === null) return null;

  if (showSplash) {
    return <SplashScreen onGuest={() => setShowSplash(false)} deleted={deleted} />;
  }

  return (
    <main className="min-h-screen flex flex-col bg-zinc-950">
      <Nav />

      {/* ── Platform toggle ── */}
      <div className="flex justify-center pt-8 px-4">
        <div className="flex bg-zinc-900 border border-zinc-800 rounded-full p-1 gap-1">
          {(["tiktok", "instagram"] as Platform[]).map((p) => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={`px-6 py-2 rounded-full text-sm font-semibold transition-all duration-200 ${
                platform === p
                  ? "bg-purple-600 text-white shadow-sm"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              {PLATFORM_LABEL[p]}
            </button>
          ))}
        </div>
      </div>

      {/* ── Hero ── */}
      <section className="flex flex-col items-center px-4 pt-10 pb-6 text-center">
        <h1 className="text-3xl font-bold text-white tracking-tight">
          Analyze your next {PLATFORM_LABEL[platform]} video
        </h1>
        <p className="text-zinc-400 text-sm mt-2">
          Drop your video and get an AI score in seconds.
        </p>
      </section>

      {/* ── Upload form ── */}
      <section className="flex-1 px-4 pb-16">
        <UploadZone platform={platform} />
        <p className="text-zinc-600 text-xs text-center mt-5 max-w-xl mx-auto">
          Your video is analyzed privately and not stored permanently.
        </p>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-zinc-800 px-4 py-8">
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-zinc-600">
          <span>© {new Date().getFullYear()} Surge</span>
          <div className="flex items-center gap-4">
            <Link href="/privacy" className="hover:text-zinc-400 transition-colors">Privacy Policy</Link>
            <Link href="/terms"   className="hover:text-zinc-400 transition-colors">Terms of Service</Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
