"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import UploadZone from "@/components/UploadZone";
import Nav from "@/components/Nav";
import { getToken } from "@/lib/auth";

type Platform = "tiktok" | "instagram";

const PLATFORM_CONFIG = {
  tiktok: {
    icon: "🎵",
    label: "TikTok",
    badge: "AI-Powered TikTok Scoring",
    headline: (
      <>
        Will your TikTok{" "}
        <span className="gradient-text">go viral?</span>
      </>
    ),
    sub: "Upload your TikTok video and get an instant AI-powered performance prediction — hook strength, pacing, audio, captions, trend alignment, and more.",
    uploadDesc: "Drop any .mp4 or .mov TikTok video up to 100MB.",
  },
  instagram: {
    icon: "📸",
    label: "Instagram",
    badge: "AI-Powered Instagram Scoring",
    headline: (
      <>
        Will your Reel{" "}
        <span className="gradient-text">blow up?</span>
      </>
    ),
    sub: "Upload your Instagram Reel and get an instant AI-powered performance prediction — saves, shares, Explore reach, aesthetic score, and more.",
    uploadDesc: "Drop any .mp4 or .mov Instagram Reel up to 100MB.",
  },
};

// ─── Splash screen ────────────────────────────────────────────────────────────

function SplashScreen({ onGuest }: { onGuest: () => void }) {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 bg-background">
      <div className="w-full max-w-md text-center space-y-10">
        {/* Branding */}
        <div className="space-y-4">
          <div className="text-6xl">🎬</div>
          <h1 className="text-5xl font-extrabold gradient-text tracking-tight">
            Surge
          </h1>
          <p className="text-text-muted text-lg leading-relaxed max-w-sm mx-auto">
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
              className="bg-surface border border-border text-text-muted text-xs px-3 py-1.5 rounded-full"
            >
              {f}
            </span>
          ))}
        </div>

        {/* CTAs */}
        <div className="space-y-3">
          {/* Primary — most appealing */}
          <Link
            href="/signup"
            className="block w-full gradient-btn text-white font-bold py-4 rounded-xl text-lg shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-transform"
          >
            Create free account
          </Link>

          {/* Secondary */}
          <Link
            href="/login"
            className="block w-full bg-card border border-border text-text-primary font-semibold py-3 rounded-xl hover:border-purple-from/50 transition-colors"
          >
            Log in
          </Link>

          {/* Least appealing — guest */}
          <div className="pt-2">
            <button
              onClick={onGuest}
              className="text-text-muted/60 text-sm hover:text-text-muted transition-colors"
            >
              Continue as guest
            </button>
            <p className="text-text-muted/40 text-xs mt-1">
              Results are locked · no history saved
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Home() {
  const [platform, setPlatform] = useState<Platform>("tiktok");
  // null = still checking localStorage (avoids flash); true = show splash; false = show app
  const [showSplash, setShowSplash] = useState<boolean | null>(null);

  useEffect(() => {
    // If a valid token exists the user is already logged in — skip the splash entirely.
    // localStorage persists across tab closes, so reopening the tab keeps them signed in.
    setShowSplash(!getToken());
  }, []);

  // Nothing rendered until we know whether to show splash (avoids layout flash)
  if (showSplash === null) return null;

  if (showSplash) {
    return <SplashScreen onGuest={() => setShowSplash(false)} />;
  }

  const cfg = PLATFORM_CONFIG[platform];

  return (
    <main className="min-h-screen flex flex-col">
      <Nav />

      {/* Platform Switcher */}
      <div className="flex justify-center pt-6 px-4">
        <div className="flex bg-card border border-border rounded-2xl p-1 gap-1">
          {(["tiktok", "instagram"] as Platform[]).map((p) => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                platform === p
                  ? "gradient-btn text-white shadow-sm"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              <span>{PLATFORM_CONFIG[p].icon}</span>
              {PLATFORM_CONFIG[p].label}
            </button>
          ))}
        </div>
      </div>

      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center px-4 py-16 text-center">
        <div className="max-w-3xl mx-auto space-y-8">
          <div className="space-y-4">
            <div className="inline-block bg-purple-from/20 border border-purple-from/30 text-purple-to text-xs font-semibold px-3 py-1 rounded-full mb-2 uppercase tracking-wide">
              {cfg.badge}
            </div>
            <h1 className="text-5xl md:text-7xl font-extrabold leading-tight">
              {cfg.headline}
            </h1>
            <p className="text-text-muted text-lg md:text-xl max-w-xl mx-auto leading-relaxed">
              {cfg.sub}
            </p>
          </div>

          {/* Stats row */}
          <div className="flex justify-center gap-8 text-center">
            {[
              { value: "6", label: "Score metrics" },
              { value: "AI", label: "Gemini powered" },
              { value: "30s", label: "Analysis time" },
            ].map((s) => (
              <div key={s.label}>
                <div className="text-2xl font-bold gradient-text">{s.value}</div>
                <div className="text-text-muted text-xs mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Upload zone */}
          <div className="w-full">
            <UploadZone platform={platform} />
          </div>

          <p className="text-text-muted text-xs">
            Your video is analyzed privately and not stored permanently.
          </p>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-border bg-surface/30 px-4 py-16">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-bold text-center text-text-primary mb-10">
            How it works
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                icon: "📤",
                title: "Upload your video",
                desc: cfg.uploadDesc,
              },
              {
                icon: "🤖",
                title: "AI analyzes it",
                desc: "Google Gemini 2.5 Flash reviews hook, pacing, audio, captions, and trend alignment.",
              },
              {
                icon: "📈",
                title: "Get your score",
                desc: "Receive a full performance breakdown with specific, actionable improvements.",
              },
            ].map((step) => (
              <div
                key={step.title}
                className="bg-card border border-border rounded-2xl p-6 text-center"
              >
                <div className="text-4xl mb-3">{step.icon}</div>
                <h3 className="font-semibold text-text-primary mb-1">
                  {step.title}
                </h3>
                <p className="text-text-muted text-sm">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
