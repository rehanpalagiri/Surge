"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { UploadCloud, CheckCircle2, Lock } from "lucide-react";
import UploadZone from "@/components/UploadZone";
import Nav from "@/components/Nav";
import { getToken } from "@/lib/auth";
import { analyzeVideo, wakeBackend } from "@/lib/api";

type Platform = "tiktok" | "instagram";

const PLATFORM_LABEL: Record<Platform, string> = {
  tiktok: "TikTok",
  instagram: "Instagram",
};

const NICHE_CHIPS = ["Fitness", "Comedy", "Gaming", "Food", "Fashion", "Lifestyle"];

const PROCESSING_STEPS = [
  "Analyzing first 3-second hook...",
  "Scanning for UI text collisions...",
  "Calculating pacing fatigue...",
  "Generating final retention report...",
];

// ─── Processing overlay ────────────────────────────────────────────────────────

function ProcessingOverlay({ step }: { step: number }) {
  return (
    <div className="fixed inset-0 z-50 bg-zinc-950/98 backdrop-blur-sm flex flex-col items-center justify-center gap-8 px-6">
      {/* Spinner */}
      <div className="relative">
        <div className="w-20 h-20 rounded-full border-4 border-purple-500/20 border-t-purple-500 animate-spin" />
        <div className="absolute inset-0 flex items-center justify-center text-2xl">🎬</div>
      </div>

      {/* Step text */}
      <div className="text-center space-y-2">
        <p className="text-white text-xl font-bold animate-pulse">
          {PROCESSING_STEPS[step] ?? PROCESSING_STEPS[PROCESSING_STEPS.length - 1]}
        </p>
        <p className="text-zinc-500 text-sm">Hang tight — this takes about 15 seconds</p>
      </div>

      {/* Step indicator dots */}
      <div className="flex gap-2">
        {PROCESSING_STEPS.map((_, i) => (
          <div
            key={i}
            className={`h-1.5 rounded-full transition-all duration-500 ${
              i === step ? "w-8 bg-purple-500" : i < step ? "w-3 bg-purple-500/40" : "w-3 bg-zinc-700"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Landing hero (anonymous users) ───────────────────────────────────────────

function LandingHero({ deleted }: { deleted: boolean }) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [niche, setNiche] = useState("");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [processing, setProcessing] = useState(false);
  const [processingStep, setProcessingStep] = useState(0);

  // Cycle through processing steps every 4 seconds
  useEffect(() => {
    if (!processing) return;
    setProcessingStep(0);
    const interval = setInterval(() => {
      setProcessingStep((s) => Math.min(s + 1, PROCESSING_STEPS.length - 1));
    }, 4000);
    return () => clearInterval(interval);
  }, [processing]);

  const handleFile = (f: File) => {
    setError("");
    setFile(f);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Upload an MP4 or .MOV to get started.");
      return;
    }
    setError("");
    setProcessing(true);

    try {
      await wakeBackend();
      const { id } = await analyzeVideo(file, niche || "Lifestyle & Vlogs");
      router.push(`/results/${id}`);
    } catch (err: unknown) {
      setProcessing(false);
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("429")) {
        setError("You've used your free analyses for today. Sign up free to get more.");
      } else {
        setError(msg || "Analysis failed. Please try again.");
      }
    }
  };

  return (
    <>
      {processing && <ProcessingOverlay step={processingStep} />}

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
              className="bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold px-4 py-1.5 rounded-lg transition-colors"
            >
              Sign up free
            </Link>
          </div>
        </header>

        {deleted && (
          <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-sm px-5 py-3 rounded-xl shadow-lg">
            Your account has been deleted.
          </div>
        )}

        {/* ── Hero ── */}
        <section className="flex-1 flex flex-col items-center justify-center px-4 py-12">
          <div className="w-full max-w-2xl space-y-8 text-center">

            {/* Badge */}
            <div className="inline-flex items-center gap-2 bg-purple-500/10 border border-purple-500/20 text-purple-400 text-xs font-semibold px-4 py-1.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
              AI-powered · Free · Results in 15 seconds
            </div>

            {/* Headline */}
            <div className="space-y-4">
              <h1 className="text-4xl sm:text-5xl font-extrabold text-white leading-tight tracking-tight">
                Find Out Exactly Where Your<br />
                <span className="text-purple-400">Viewers Are Scrolling Away.</span>
              </h1>
              <p className="text-zinc-400 text-lg max-w-xl mx-auto leading-relaxed">
                Upload your video before you post it. Our AI engine analyzes your pacing, hook
                velocity, and UI collisions in 15 seconds to predict your viral potential.
              </p>
            </div>

            {/* ── Input zone ── */}
            <form onSubmit={handleSubmit} className="space-y-4 text-left">

              {/* File drop zone */}
              <div
                onDrop={onDrop}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onClick={() => fileInputRef.current?.click()}
                className={`cursor-pointer rounded-2xl border-2 transition-all duration-200 p-10 flex flex-col items-center justify-center gap-3 text-center min-h-[180px]
                  ${dragging
                    ? "border-purple-500 bg-purple-500/10"
                    : file
                    ? "border-emerald-500 bg-emerald-500/5"
                    : "border-dashed border-zinc-700 bg-zinc-900 hover:border-purple-500 hover:bg-purple-500/5"
                  }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="video/*"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                />
                {file ? (
                  <>
                    <CheckCircle2 className="w-10 h-10 text-emerald-400 flex-shrink-0" strokeWidth={1.5} />
                    <p className="text-white font-semibold text-sm">{file.name}</p>
                    <p className="text-zinc-500 text-xs">Tap to change file</p>
                  </>
                ) : (
                  <>
                    <UploadCloud className={`w-10 h-10 flex-shrink-0 ${dragging ? "text-purple-400" : "text-zinc-500"}`} strokeWidth={1.5} />
                    <div className="space-y-1">
                      <p className="text-white font-semibold text-base">
                        <span className="sm:hidden">Tap to upload your video</span>
                        <span className="hidden sm:block">Drop your video here or click to browse</span>
                      </p>
                      <p className="text-zinc-500 text-sm">.mp4 or .mov · up to 10 min</p>
                    </div>
                  </>
                )}
              </div>

              {/* Niche chips (optional) */}
              <div>
                <p className="text-zinc-500 text-xs mb-2">Content niche <span className="text-zinc-600">(optional)</span></p>
                <div className="flex flex-wrap gap-2">
                  {NICHE_CHIPS.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setNiche(niche === n ? "" : n)}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                        niche === n
                          ? "bg-purple-600 text-white"
                          : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-white"
                      }`}
                    >
                      {n}
                    </button>
                  ))}
                </div>
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
                className="w-full bg-purple-600 hover:bg-purple-500 text-white font-bold py-4 rounded-2xl text-lg transition-all
                  hover:shadow-[0_0_20px_rgba(168,85,247,0.5)]
                  disabled:opacity-50 disabled:cursor-not-allowed
                  active:scale-[0.99]"
              >
                Analyze My Video →
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
    return <LandingHero deleted={deleted} />;
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
