"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Lock } from "lucide-react";
import UploadZone from "@/components/UploadZone";
import NichePicker from "@/components/NichePicker";
import Nav from "@/components/Nav";
import { getToken } from "@/lib/auth";
import { analyzeVideo, wakeBackend } from "@/lib/api";
import { isAllowedVideoFile } from "@/lib/videoValidation";
import { AnalysisOverlay } from "@/components/AnalysisProgress";
import { Skeleton, SkeletonCard, SkeletonMedia, SkeletonTitle } from "@/components/Skeleton";
import ReactiveVideoDropzone from "@/components/ReactiveVideoDropzone";
import PlatformTabs from "@/components/PlatformTabs";
import { track } from "@vercel/analytics";

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

  const [file, setFile] = useState<File | null>(null);
  const [niches, setNiches] = useState<string[]>([]);  // up to 2; first = primary, second = blend
  const [showRubricHint, setShowRubricHint] = useState(false);
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
    track("upload_started", { platform: "tiktok", niche_count: niches.length, logged_in: false });
    setProcessing(true);

    try {
      await wakeBackend();
      const { id } = await analyzeVideo(
        file,
        niches[0] ?? "",
        "", "", "tiktok", "",
        niches[1] ?? "",
      );
      track("analysis_complete", { platform: "tiktok", mode: "direct" });
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

      <main className="min-h-screen flex flex-col bg-zinc-950">
        {/* ── Minimal nav ── */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-zinc-900">
          <span className="text-xl font-extrabold text-purple-500 tracking-tight">Surge</span>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-zinc-400 text-sm hover:text-white transition-colors">
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
          <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-sm px-5 py-3 rounded-xl shadow-lg flex items-center gap-3">
            Your account has been deleted.
            <button
              onClick={onDismissDeleted}
              className="text-emerald-400/60 hover:text-emerald-400 transition-colors leading-none"
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
            <div className="inline-flex items-center gap-2 bg-purple-500/10 border border-purple-500/20 text-purple-400 text-xs font-semibold px-4 py-1.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
              AI-assisted · Free · Pre-post craft review
            </div>

            {/* Headline */}
            <div className="space-y-3 sm:space-y-4">
              <h1 className="text-3xl sm:text-5xl font-extrabold text-white leading-tight tracking-tight">
                Find Where Viewers{" "}
                <span className="text-purple-400">Might Drift.</span>
              </h1>
              <p className="text-zinc-400 text-base sm:text-lg max-w-xl mx-auto leading-relaxed">
                Review the hook, pacing, text, tension, sync, and ending before posting, then
                choose one retention-focused experiment for the next version.
              </p>
            </div>

            {/* ── Input zone ── */}
            <form onSubmit={handleSubmit} className="space-y-4 text-left">

              {/* File drop zone */}
              <ReactiveVideoDropzone
                file={file}
                onFileSelected={handleFile}
                selectedDetail={file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB · validation passed` : undefined}
              />

              {/* Optional rubric hint */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3">
                {showRubricHint || niches.length > 0 ? (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Rubric Hint</p>
                        <p className="text-[11px] text-zinc-500">Optional — Surge can detect this automatically</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setNiches([]);
                          setShowRubricHint(false);
                        }}
                        className="text-xs font-medium text-zinc-500 hover:text-zinc-300 transition-colors"
                      >
                        Auto-detect
                      </button>
                    </div>
                    <NichePicker selected={niches} onChange={setNiches} />
                  </div>
                ) : (
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-zinc-300">Surge will auto-detect the rubric</p>
                      <p className="text-xs text-zinc-500">Add a hint only if this video is easy to misread.</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowRubricHint(true)}
                      className="shrink-0 rounded-lg border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-300 hover:border-purple-400 hover:text-white transition-colors"
                    >
                      Add hint
                    </button>
                  </div>
                )}
              </div>

              {/* Error */}
              {error && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 text-red-400 text-sm">
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
            </form>

            {/* Trust signals */}
            <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-zinc-600 text-xs pt-2">
              <span className="flex items-center gap-1.5">
                <Lock className="w-3 h-3" /> Video analyzed privately
              </span>
              <span>·</span>
              <span>No account required</span>
              <span>·</span>
              <Link href="/sample" className="hover:text-zinc-400 underline transition-colors">
                See a sample report →
              </Link>
            </div>

          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-zinc-900 px-6 py-5">
          <div className="max-w-2xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-zinc-700">
            <span>© {new Date().getFullYear()} Surge</span>
            <div className="flex gap-4">
              <Link href="/privacy" className="hover:text-zinc-500 transition-colors">Privacy</Link>
              <Link href="/terms" className="hover:text-zinc-500 transition-colors">Terms</Link>
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
  const [reanalyzeNiches, setReanalyzeNiches] = useState<string[] | undefined>(undefined);

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
    const nicheParam = params.get("niche");
    const platformParam = params.get("platform") as Platform | null;
    if (parentParam && /^\d+$/.test(parentParam)) {
      setReanalyzeParentId(Number(parentParam));
      if (nicheParam) setReanalyzeNiches([nicheParam]);
      if (platformParam && (platformParam === "tiktok" || platformParam === "instagram")) {
        setPlatform(platformParam);
      }
      window.history.replaceState({}, "", "/");
    }
  }, []);

  if (showSplash === null) {
    return (
      <main className="min-h-screen bg-zinc-950" aria-busy="true" aria-label="Checking account session">
        <header className="border-b border-zinc-900 px-6 py-4">
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
    <main className="min-h-screen flex flex-col bg-zinc-950">
      <Nav />

      {/* ── Platform toggle ── */}
      <div className="flex justify-center pt-8 px-4">
        <PlatformTabs value={platform} onChange={setPlatform} />
      </div>

      {/* ── Hero ── */}
      <section className="flex flex-col items-center px-4 pt-10 pb-6 text-center">
        <h1 className="text-3xl font-bold text-white tracking-tight">
          Analyze your next {PLATFORM_LABEL[platform]} video
        </h1>
        <p className="text-zinc-400 text-sm mt-2">
          Find attention risks and one retention-focused experiment to test next.
        </p>
      </section>

      {/* ── Upload form ── */}
      <section className="flex-1 px-4 pb-16">
        <UploadZone
          platform={platform}
          parentId={reanalyzeParentId}
          initialNiches={reanalyzeNiches}
        />
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
