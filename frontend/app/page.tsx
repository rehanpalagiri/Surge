"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Eye, Lock, Play, Sparkles, Target, LineChart, Upload, Zap } from "lucide-react";
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

function LegacyLandingHero({ deleted, onDismissDeleted }: { deleted: boolean; onDismissDeleted: () => void }) {
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

// ─── Premium anonymous landing page ──────────────────────────────────────────

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
    if (!file) { setError("Upload a video to get started — MP4, MOV, WEBM, AVI & more."); return; }
    setError("");
    track("upload_started", { platform, niche_count: 0, logged_in: false });
    setProcessing(true);
    try {
      await wakeBackend();
      const { id } = await analyzeVideo(file, "", "", "", platform, "", "");
      track("analysis_complete", { platform, mode: "direct" });
      router.push(`/results/${id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "";
      track("upload_error", { error_type: msg.includes("429") ? "rate_limit" : msg.includes("400") ? "validation" : "other" });
      setProcessing(false);
      if (msg.includes("429")) setError("You've used your free analyses for today. Sign up free to get more.");
      else if (msg.includes("400")) setError(formatBadRequestMessage(msg));
      else setError(msg || "Analysis failed. Please try again.");
    }
  };

  return (
    <>
      {processing && <AnalysisOverlay active={processing} steps={PROCESSING_STEPS} />}
      <main className="surge-landing min-h-screen bg-background">
        <header className="surge-nav">
          <Link href="/" className="surge-brand" aria-label="Surge home"><span className="surge-brand-mark">↯</span> surge</Link>
          <nav><a href="#how">How it works</a><a href="#report">Sample report</a><Link href="/login">Log in</Link><Link className="surge-nav-cta" href="/signup">Sign up free <ArrowRight size={15}/></Link></nav>
        </header>

        {deleted && <div className="surge-toast">Your account has been deleted.<button onClick={onDismissDeleted} aria-label="Dismiss">×</button></div>}

        <section className="surge-hero">
          <div className="surge-hero-copy">
            <div className="surge-eyebrow"><Sparkles size={14}/> BUILT FOR SHORT-FORM CREATORS</div>
            <h1>Your next post<br/>shouldn&apos;t lose them <em>here.</em></h1>
            <p>Surge finds the exact moments costing you attention—and tells you what to change <strong>before you post.</strong></p>
            <div className="surge-actions"><a className="surge-primary" href="#upload">Analyze my video <ArrowRight size={18}/></a><a className="surge-demo" href="#report"><span><Play size={14}/></span> See a sample report</a></div>
            <div className="surge-trust"><span><Check size={13}/> 3 free analyses</span><span><Lock size={13}/> Videos stay private</span><span>No card</span></div>
          </div>

          <div className="surge-monitor" aria-label="Example Surge craft review">
            <div className="surge-monitor-bar"><span className="surge-dots">● ● ●</span><span>surge / craft review</span><span className="surge-live"><b/> Review ready</span></div>
            <div className="surge-monitor-body">
              <div className="surge-video-frame"><div className="surge-video-copy">3 editing tricks<br/><b>nobody tells you</b></div><div className="surge-person"/><div className="surge-timeline"><span>0:09</span><i/></div><label><Eye size={11}/> Attention risk</label></div>
              <div className="surge-analysis"><div className="surge-analysis-head"><span>Attention risk map</span><b>0:08–0:12</b></div><div className="surge-chart"><i/><i/><i/><svg viewBox="0 0 360 120" preserveAspectRatio="none" aria-hidden><path d="M0 15 C40 20 65 25 96 31 S145 45 172 45 S205 42 226 72 S270 81 300 91 S330 98 360 108"/><circle cx="226" cy="72" r="5"/></svg></div><div className="surge-finding"><span>HIGH RISK · TEXT SCANNABILITY</span><strong>Your caption sits in TikTok&apos;s UI zone.</strong><p>Move it to the upper third and tighten the pause.</p></div><button>Show me the fix <ArrowRight size={15}/></button></div>
            </div>
            <div className="surge-float surge-float-a"><Sparkles size={14}/> AI craft analysis</div><div className="surge-float surge-float-b"><b>+24%</b> clearer hook</div>
          </div>
        </section>

        <div className="surge-platforms"><span>BUILT FOR THE FEEDS YOU CARE ABOUT</span><div><b>♪ TikTok</b><b>◎ Instagram Reels</b></div></div>

        <section className="surge-upload-wrap" id="upload">
          <div className="surge-section-heading"><span>YOUR FIRST WIN</span><h2>See what your viewers see.</h2><p>No dashboards. No guesswork. Drop a draft and get a clear edit list in under a minute.</p></div>
          <form onSubmit={handleSubmit} className="surge-upload-card">
            <div className="surge-platform-tabs"><button type="button" className={platform === "tiktok" ? "active" : ""} onClick={() => setPlatform("tiktok")}>♪ TikTok</button><button type="button" className={platform === "instagram" ? "active" : ""} onClick={() => setPlatform("instagram")}>◎ Instagram</button></div>
            <ReactiveVideoDropzone file={file} onFileSelected={handleFile} selectedDetail={file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB · validation passed` : undefined}/>
            {error && <div className="surge-error">{error}</div>}
            <button type="submit" disabled={processing} className="surge-submit">{file ? "Find my attention leaks" : "Choose a video to continue"}<ArrowRight size={18}/></button>
            <div className="surge-privacy"><Lock size={13}/> Encrypted in transit · Automatically deleted after analysis</div>
          </form>
        </section>

        <section className="surge-how" id="how"><div className="surge-section-heading surge-left"><span>HOW IT WORKS</span><h2>From rough cut to<br/><em>ready to post.</em></h2></div><div className="surge-step-grid"><article><b>01</b><div className="surge-step-art"><Upload size={25}/><i/><i/><i/></div><h3>Drop your draft</h3><p>Upload the version sitting in your camera roll. No account needed.</p></article><article><b>02</b><div className="surge-step-art scan"><span>Scanning hook</span><i/></div><h3>Surge reads the edit</h3><p>We review hook, pacing, captions, tension, sync, and ending.</p></article><article><b>03</b><div className="surge-step-art fix"><Check size={25}/><i/><i/><i/></div><h3>Fix what matters</h3><p>Get timestamped changes you can make before your next post.</p></article></div></section>

        <section className="surge-report" id="report"><div className="surge-report-inner"><div className="surge-report-copy"><span>AN ACTUAL SURGE REPORT</span><h2>Feedback that speaks<br/>creator, <em>not corporate.</em></h2><p>Every review turns six craft signals into one clear next experiment.</p><div className="surge-score-list">{SAMPLE_SCORES.slice(0, 4).map((sc) => <div key={sc.label}><span>{sc.label}</span><b>{sc.score}/10</b><i><em style={{ width: `${sc.score * 10}%` }}/></i></div>)}</div></div><div className="surge-report-card"><div><span>BIGGEST ATTENTION LEAK · {SAMPLE_RISK.section}</span><h3>Make the moment easier to read.</h3><p>{SAMPLE_RISK.reason}</p></div><a href="/sample">Explore the full sample report <ArrowRight size={16}/></a></div></div></section>

        <section className="surge-final"><span className="surge-brand-mark large">↯</span><h2>Your better edit is<br/><em>one upload away.</em></h2><p>Find the moment they&apos;ll scroll—before they do.</p><a className="surge-primary" href="#upload">Analyze my first video <ArrowRight size={18}/></a><small>Free · no card · under 60 seconds</small></section>
        <footer className="surge-footer"><Link href="/" className="surge-brand"><span className="surge-brand-mark">↯</span> surge</Link><span>Make every second count.</span><div><Link href="/pricing">Pricing</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></div><small>© {new Date().getFullYear()} Surge</small></footer>
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
