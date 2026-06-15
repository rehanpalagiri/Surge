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
    badge: "AI-Powered TikTok Analysis",
    headlinePre: "Will your TikTok",
    headlineAccent: "go viral?",
    sub: "Upload your TikTok and get an instant AI breakdown — hook strength, pacing, audio, captions, trend alignment, and a full improvement plan.",
    uploadDesc: "Drop any .mp4 or .mov TikTok video up to 100MB.",
    textGradient: "gradient-text-tiktok",
    btnGradient: "gradient-btn-tiktok",
    badgeClass: "bg-[#fe2c55]/10 border-[#fe2c55]/40 text-[#fe2c55]",
    // Near-black page bg — the real TikTok aesthetic
    pageBg: "bg-[#010101]",
    // Glitch class on the accent headline word
    accentClass: "tiktok-glitch",
    // Per-stat colours — alternating cyan / red / cyan
    statColors: ["tiktok-cyan", "tiktok-red", "tiktok-cyan"],
    uploadZoneExtra: "tiktok-glow",
  },
  instagram: {
    icon: "📸",
    label: "Instagram",
    badge: "AI-Powered Instagram Scoring",
    headlinePre: "Will your Reel",
    headlineAccent: "blow up?",
    sub: "Upload your Instagram Reel and get an instant AI-powered performance prediction — saves, shares, Explore reach, aesthetic score, and more.",
    uploadDesc: "Drop any .mp4 or .mov Instagram Reel up to 100MB.",
    textGradient: "gradient-text-instagram",
    btnGradient: "gradient-btn-instagram",
    badgeClass: "bg-[#fd1d1d]/10 border-[#fcaf45]/30 text-[#fcaf45]",
    pageBg: "bg-background",
    accentClass: "gradient-text-instagram",
    statColors: ["gradient-text-instagram", "gradient-text-instagram", "gradient-text-instagram"],
    uploadZoneExtra: "",
  },
};

// ─── Splash screen ────────────────────────────────────────────────────────────

function SplashScreen({ onGuest, deleted }: { onGuest: () => void; deleted: boolean }) {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 bg-background">
      {deleted && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 bg-success/10 border border-success/30 text-success text-sm px-5 py-3 rounded-xl shadow-lg">
          Your account has been deleted.
        </div>
      )}
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

          {/* Sample report link */}
          <p className="text-text-muted/40 text-xs pt-1">
            Not sure what you&apos;ll get?{" "}
            <Link href="/sample" className="hover:text-text-muted underline transition-colors">
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
  // null = still checking localStorage (avoids flash); true = show splash; false = show app
  const [showSplash, setShowSplash] = useState<boolean | null>(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [deleted, setDeleted] = useState(false);

  useEffect(() => {
    const token = getToken();
    setShowSplash(!token);
    setIsLoggedIn(!!token);
    const params = new URLSearchParams(window.location.search);
    if (params.get("deleted") === "1") {
      setDeleted(true);
      window.history.replaceState({}, "", "/");
    }
  }, []);

  // Nothing rendered until we know whether to show splash (avoids layout flash)
  if (showSplash === null) return null;

  if (showSplash) {
    return <SplashScreen onGuest={() => setShowSplash(false)} deleted={deleted} />;
  }

  const cfg = PLATFORM_CONFIG[platform];

  return (
    <main className={`min-h-screen flex flex-col transition-colors duration-300 ${cfg.pageBg}`}>
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
                  ? `${PLATFORM_CONFIG[p].btnGradient} text-white shadow-sm`
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              <span>{PLATFORM_CONFIG[p].icon}</span>
              {PLATFORM_CONFIG[p].label}
            </button>
          ))}
        </div>
      </div>

      {/* Hero — abbreviated for logged-in users, full marketing pitch for guests */}
      <section id="upload" className="flex-1 flex flex-col items-center justify-center px-4 py-8 sm:py-14 text-center scroll-mt-20">
        <div className="max-w-3xl mx-auto space-y-8">
          {isLoggedIn ? (
            /* Compact header — logged-in users already know what Surge does */
            <div className="space-y-1">
              <h1 className="text-3xl font-bold text-text-primary">
                Analyze your next {cfg.label} video
              </h1>
              <p className="text-text-muted text-sm">
                Drop your video and get an AI score in seconds.
              </p>
            </div>
          ) : (
            /* Full marketing hero for guests */
            <div className="space-y-4">
              <div
                className={`inline-block border text-xs font-semibold px-3 py-1 rounded-full mb-2 uppercase tracking-widest ${cfg.badgeClass}`}
              >
                {cfg.badge}
              </div>
              <h1 className="text-5xl md:text-7xl font-extrabold leading-tight">
                {cfg.headlinePre}{" "}
                <span className={cfg.accentClass}>{cfg.headlineAccent}</span>
              </h1>
              <p className="text-text-muted text-lg md:text-xl max-w-xl mx-auto leading-relaxed">
                {cfg.sub}
              </p>
            </div>
          )}

          {/* Upload zone */}
          <div className={`w-full rounded-2xl ${cfg.uploadZoneExtra}`}>
            <UploadZone platform={platform} />
          </div>

          <p className="text-text-muted text-xs">
            Your video is analyzed privately and not stored permanently.
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border px-4 py-8">
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-text-muted/60">
          <span>© {new Date().getFullYear()} Surge</span>
          <div className="flex items-center gap-4">
            <Link href="/privacy" className="hover:text-text-muted transition-colors">Privacy Policy</Link>
            <Link href="/terms" className="hover:text-text-muted transition-colors">Terms of Service</Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
