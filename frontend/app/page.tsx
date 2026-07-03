"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Lock, Target, LineChart, Zap } from "lucide-react";
import UploadZone from "@/components/UploadZone";
import Nav from "@/components/Nav";
import { getToken } from "@/lib/auth";
import { analyzeVideo, wakeBackend } from "@/lib/api";
import { isAllowedVideoFile } from "@/lib/videoValidation";
import { AnalysisOverlay } from "@/components/AnalysisProgress";
import { Skeleton, SkeletonCard, SkeletonMedia, SkeletonTitle } from "@/components/Skeleton";
import ReactiveVideoDropzone from "@/components/ReactiveVideoDropzone";
import PlatformTabs from "@/components/PlatformTabs";
import { track } from "@vercel/analytics";
import ScoreBar from "@/components/ScoreBar";
import { SAMPLE_SCORES, SAMPLE_RISK } from "@/lib/sampleReport";

type Platform = "tiktok" | "instagram";

const PLATFORM_LABEL: Record<Platform, string> = {
  tiktok: "TikTok",
  instagram: "Instagram",
};

const PROCESSING_STEPS = [
  "Analyzing the first-3-second hook…",
  "Scanning for on-screen text collisions…",
  "Measuring cut rhythm and pacing…",
  "Checking audio-visual sync and the ending…",
  "Writing your craft review…",
];

// ─── Landing hero (anonymous users) ───────────────────────────────────────────

const MAX_BYTES = 100 * 1024 * 1024;

function formatBadRequestMessage(msg: string) {
  const detail = msg.replace(/^API error 400:\s*/, "");
  try {
    const parsed = JSON.parse(detail);
    if (typeof parsed?.detail === "string") return parsed.detail;
  } catch {
    // Plain-text API errors are already suitable for display.
  }
  return detail || "Analysis failed. Please try again.";
}

function LandingHero({ deleted, onDismissDeleted }: { deleted: boolean; onDismissDeleted: () => void }) {
  const router = useRouter();

  const [platform, setPlatform] = useState<Platform>("tiktok");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [processing, setProcessing] = useState(false);

  const handleFile = async (f: File) => {
    setError("");

    if (!isAllowedVideoFile(f)) {
      setError("Please upload a supported video file (MP4, MOV, WEBM, AVI & more).");
      return;
    }

    if (f.size > MAX_BYTES) {
      setError("Your video is too large. Maximum size is 100 MB — try exporting at 720p from your camera app.");
      return;
    }

    const duration = await new Promise<number>((resolve) => {
      const video = document.createElement("video");
      video.preload = "metadata";
      const url = URL.createObjectURL(f);
      video.onloadedmetadata = () => { URL.revokeObjectURL(url); resolve(video.duration); };
      video.onerror = () => { URL.revokeObjectURL(url); resolve(0); };
      video.src = url;
    });

    if (duration > 600) {
      setError("Your video is over 10 minutes. Please trim it before uploading.");
      return;
    }

    setFile(f);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Upload a video to get started — MP4, MOV, WEBM, AVI & more.");
      return;
    }
    setError("");
    track("upload_started", { platform, niche_count: 0, logged_in: false });
    setProcessing(true);

    try {
      await wakeBackend();
      const { id } = await analyzeVideo(
        file,
        "",
        "", "", platform, "",
        "",
      );
      track("analysis_complete", { platform, mode: "direct" });
      router.push(`/results/${id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "";
      track("upload_error", { error_type: msg.includes("429") ? "rate_limit" : msg.includes("400") ? "validation" : "other" });
      setProcessing(false);
      if (msg.includes("429")) {
        setError("You've used your free analyses for today. Sign up free to get more.");
      } else if (msg.includes("400")) {
        setError(formatBadRequestMessage(msg));
      } else {
        setError(msg || "Analysis failed. Please try again.");
      }
    }
  };

  return (
    <>
      {processing && <AnalysisOverlay active={processing} steps={PROCESSING_STEPS} />}

      <main className="min-h-screen flex flex-col bg-background">
        {/* ── Minimal nav ── */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-border">
          <span className="text-xl font-extrabold text-text-primary tracking-tight font-display">Surge</span>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-text-muted text-sm hover:text-text-primary transition-colors">
              Log in
            </Link>
            <Link
              href="/signup"
              className="gradient-btn text-white text-sm font-semibold px-4 py-1.5 rounded-lg"
            >
              Sign up free
            </Link>
          </div>
        </header>

        {deleted && (
          <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 bg-success/10 border border-success/30 text-success text-sm px-5 py-3 rounded-xl shadow-lg flex items-center gap-3">
            Your account has been deleted.
            <button
              onClick={onDismissDeleted}
              className="text-success/60 hover:text-success transition-colors leading-none"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        )}

        {/* ── Hero ── */}
        <section className="flex-1 flex flex-col items-center justify-center px-4 py-8 sm:py-12">
          <div className="w-full max-w-2xl space-y-6 sm:space-y-8 text-center">

            {/* Badge */}
            <div className="inline-flex items-center gap-2 bg-accent/10 border border-accent/20 text-accent text-xs font-semibold px-4 py-1.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              AI-assisted · Free · Pre-post craft review
            </div>

            {/* Headline */}
            <div className="space-y-3 sm:space-y-4">
              <h1 className="text-3xl sm:text-5xl font-extrabold text-text-primary leading-tight tracking-tight [text-wrap:balance]">
                Find Where Viewers{" "}
                <span className="gradient-text">Might Drift.</span>
              </h1>
              <p className="text-text-muted text-base sm:text-lg max-w-xl mx-auto leading-relaxed">
                Review the hook, pacing, text, tension, sync, and ending before posting, then
                get one retention-focused editing hypothesis to test in your next version.
              </p>
            </div>

            {/* ── Platform selector ── */}
            <div className="flex justify-center">
              <PlatformTabs value={platform} onChange={setPlatform} />
            </div>

            {/* ── Input zone ── */}
            <form onSubmit={handleSubmit} className="space-y-4 text-left">

              {/* File drop zone */}
              <ReactiveVideoDropzone
                file={file}
                onFileSelected={handleFile}
                selectedDetail={file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB · validation passed` : undefined}
              />

              {/* Error */}
              {error && (
                <div className="bg-danger/10 border border-danger/30 rounded-xl px-4 py-3 text-danger text-sm">
                  {error}
                </div>
              )}

              {/* CTA */}
              <button
                type="submit"
                disabled={processing}
                className="gradient-btn w-full text-white font-bold py-4 rounded-2xl text-lg
                  disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Review My Video →
              </button>
              <Link
                href="/sample"
                className="btn-soft block w-full text-center text-text-primary font-semibold py-3 rounded-2xl text-sm"
              >
                See a sample review
              </Link>
            </form>

            {/* Trust signals */}
            <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-text-muted text-xs pt-2">
              <span className="flex items-center gap-1.5">
                <Lock className="w-3 h-3" /> Video analyzed privately
              </span>
              <span>·</span>
              <span>No account required</span>
              <span>·</span>
              <Link href="/pricing" className="hover:text-text-primary underline transition-colors">
                3 free reviews a month — no card required
              </Link>
            </div>

            {/* Proof: a miniature of the actual product output */}
            <div className="pt-6 text-left">
              <div className="max-w-md mx-auto">
                <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">
                      What a review looks like
                    </span>
                    <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-success/10 text-success border border-success/30">
                      Strong craft
                    </span>
                  </div>
                  <div className="space-y-3">
                    {SAMPLE_SCORES.map((sc) => (
                      <ScoreBar key={sc.label} label={sc.label} score={sc.score} animate={false} />
                    ))}
                  </div>
                  <div className="border border-danger/30 bg-danger/5 rounded-xl px-3.5 py-3">
                    <p className="text-[11px] font-bold text-danger uppercase tracking-wide">
                      High risk · {SAMPLE_RISK.section}
                    </p>
                    <p className="text-text-muted text-xs mt-1 leading-relaxed">{SAMPLE_RISK.reason}</p>
                  </div>
                </div>
                <p className="text-text-muted/80 text-xs text-center mt-3">
                  From the sample review — yours is generated from your actual video.
                </p>
              </div>
            </div>

          </div>
        </section>

        {/* ── Feature row ── */}
        <section className="border-t border-border px-4 py-14 sm:py-20">
          <div className="max-w-4xl mx-auto grid grid-cols-1 sm:grid-cols-3 gap-6 sm:gap-8">
            <div className="space-y-2">
              <Target className="w-5 h-5 text-accent" />
              <h3 className="text-text-primary font-semibold text-base">Outcome-blind by design</h3>
              <p className="text-text-muted text-sm leading-relaxed">
                We critique the craft, never fake a viral score.
              </p>
            </div>

            <div className="space-y-2">
              <LineChart className="w-5 h-5 text-accent" />
              <h3 className="text-text-primary font-semibold text-base">Learn from every post</h3>
              <p className="text-text-muted text-sm leading-relaxed">
                Compare craft scores against your own verified results.
              </p>
            </div>

            <div className="space-y-2">
              <Zap className="w-5 h-5 text-accent" />
              <h3 className="text-text-primary font-semibold text-base">Private &amp; fast</h3>
              <p className="text-text-muted text-sm leading-relaxed">
                Your video is analyzed privately and not stored permanently.
              </p>
            </div>
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-border px-6 py-5">
          <div className="max-w-2xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-text-muted/80">
            <span>© {new Date().getFullYear()} Surge</span>
            <div className="flex gap-4">
              <Link href="/pricing" className="hover:text-text-primary transition-colors">Pricing</Link>
              <Link href="/privacy" className="hover:text-text-primary transition-colors">Privacy</Link>
              <Link href="/terms" className="hover:text-text-primary transition-colors">Terms</Link>
            </div>
          </div>
        </footer>
      </main>
    </>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Home() {
  const [platform, setPlatform] = useState<Platform>("tiktok");
  const [showSplash, setShowSplash] = useState<boolean | null>(null);
  const [deleted, setDeleted] = useState(false);
  const [reanalyzeParentId, setReanalyzeParentId] = useState<number | undefined>(undefined);

  useEffect(() => {
    const token = getToken();
    setShowSplash(!token);
    const params = new URLSearchParams(window.location.search);
    if (params.get("deleted") === "1") {
      setDeleted(true);
      window.history.replaceState({}, "", "/");
      const timer = setTimeout(() => setDeleted(false), 5000);
      return () => clearTimeout(timer);
    }
    // Update flow: ?parent=ID&niche=Fitness&platform=tiktok&project=Name
    const parentParam = params.get("parent");
    const platformParam = params.get("platform") as Platform | null;
    if (parentParam && /^\d+$/.test(parentParam)) {
      setReanalyzeParentId(Number(parentParam));
      if (platformParam && (platformParam === "tiktok" || platformParam === "instagram")) {
        setPlatform(platformParam);
      }
      window.history.replaceState({}, "", "/");
    }
  }, []);

  if (showSplash === null) {
    return (
      <main className="min-h-screen bg-background" aria-busy="true" aria-label="Checking account session">
        <header className="border-b border-border px-6 py-4">
          <div className="mx-auto flex max-w-5xl items-center justify-between">
            <Skeleton className="h-6 w-20 rounded-md" />
            <Skeleton className="h-9 w-24 rounded-lg" />
          </div>
        </header>
        <div className="skeleton-delay mx-auto max-w-2xl space-y-6 px-4 py-10">
          <div className="space-y-3 text-center">
            <SkeletonTitle width="62%" className="mx-auto h-9" />
            <Skeleton className="mx-auto h-4 rounded-md" width="78%" />
          </div>
          <SkeletonCard className="space-y-5">
            <SkeletonMedia className="border border-dashed border-border" />
            <Skeleton className="h-12 w-full rounded-xl" />
            <Skeleton className="h-12 w-full rounded-xl" />
          </SkeletonCard>
        </div>
      </main>
    );
  }

  if (showSplash) {
    return <LandingHero deleted={deleted} onDismissDeleted={() => setDeleted(false)} />;
  }

  return (
    <main className="min-h-screen flex flex-col bg-background">
      <Nav />

      {/* ── Platform toggle ── */}
      <div className="flex justify-center pt-8 px-4">
        <PlatformTabs value={platform} onChange={setPlatform} />
      </div>

      {/* ── Hero ── */}
      <section className="flex flex-col items-center px-4 pt-10 pb-6 text-center">
        <h1 className="text-3xl font-bold text-text-primary tracking-tight">
          Review your next {PLATFORM_LABEL[platform]} video
        </h1>
        <p className="text-text-muted text-sm mt-2">
          Find attention risks and one editing hypothesis to test in your next version.
        </p>
      </section>

      {/* ── Upload form ── */}
      <section className="flex-1 px-4 pb-16">
        <UploadZone
          platform={platform}
          parentId={reanalyzeParentId}
        />
        <p className="text-text-muted/80 text-xs text-center mt-5 max-w-xl mx-auto">
          Your video is analyzed privately and not stored permanently.
        </p>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-border px-4 py-8">
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-text-muted">
          <span>© {new Date().getFullYear()} Surge</span>
          <div className="flex items-center gap-4">
            <Link href="/pricing" className="hover:text-text-primary transition-colors">Pricing</Link>
            <Link href="/privacy" className="hover:text-text-primary transition-colors">Privacy Policy</Link>
            <Link href="/terms"   className="hover:text-text-primary transition-colors">Terms of Service</Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
