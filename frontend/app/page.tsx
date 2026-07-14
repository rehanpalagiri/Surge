"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Eye, Lock, Play, Sparkles, Target, LineChart, Upload, Zap } from "lucide-react";
import UploadZone from "@/components/UploadZone";
import Nav from "@/components/Nav";
import { getToken } from "@/lib/auth";
import { analyzeVideo, wakeBackend } from "@/lib/api";
import { isAllowedVideoFile } from "@/lib/videoValidation";
import { AnalysisOverlay } from "@/components/AnalysisProgress";
import { LandingSkeleton } from "@/components/Skeleton";
import { Tooltip } from "@/components/Tooltip";
import ReactiveVideoDropzone from "@/components/ReactiveVideoDropzone";
import PlatformTabs from "@/components/PlatformTabs";
import ProfileNudgeModal from "@/components/ProfileNudgeModal";
import ThemeToggle from "@/components/ThemeToggle";
import { track } from "@vercel/analytics";
import ScoreBar from "@/components/ScoreBar";
import BrandLogo from "@/components/BrandLogo";
import { SAMPLE_SCORES, SAMPLE_RISK } from "@/lib/sampleReport";

type Platform = "tiktok" | "instagram";

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

// ── Landing-only platform wordmarks + interactive button helpers ──
// TikTok cyan/red glitch wordmark (see .surge-glitch in globals.css).
function Glitch({ text }: { text: string }) {
  return <span className="surge-glitch" data-text={text}>{text}</span>;
}
// Instagram purple→yellow gradient wordmark (.surge-ig-gradient).
function Gradient({ text }: { text: string }) {
  return <span className="surge-ig-gradient">{text}</span>;
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Magnetic cursor-pull + click ripple; returns props to spread onto a button/anchor.
function useInteractive<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const onPointerMove = (e: React.PointerEvent<T>) => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${(e.clientX - r.left - r.width / 2) * 0.28}px`);
    el.style.setProperty("--my", `${(e.clientY - r.top - r.height / 2) * 0.28}px`);
  };
  const onPointerLeave = () => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--mx", "0px");
    el.style.setProperty("--my", "0px");
  };
  const onPointerDown = (e: React.PointerEvent<T>) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const size = Math.max(r.width, r.height);
    const ripple = document.createElement("span");
    ripple.className = "surge-ripple";
    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${e.clientX - r.left - size / 2}px`;
    ripple.style.top = `${e.clientY - r.top - size / 2}px`;
    el.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove());
  };
  return { ref, onPointerMove, onPointerLeave, onPointerDown };
}

// Kept as a rollback reference while the anonymous landing is iterated.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
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
          <BrandLogo className="text-xl" />
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

  const navCta = useInteractive<HTMLAnchorElement>();
  const heroCta = useInteractive<HTMLAnchorElement>();
  const finalCta = useInteractive<HTMLAnchorElement>();
  const submitBtn = useInteractive<HTMLButtonElement>();
  const progressRef = useRef<HTMLDivElement>(null);

  // Scroll progress bar + subtle parallax on the floating badges (rAF-throttled).
  useEffect(() => {
    const progress = progressRef.current;
    const floats = Array.from(document.querySelectorAll<HTMLElement>(".surge-float"));
    const reduce = prefersReducedMotion();
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const y = window.scrollY;
        const max = document.documentElement.scrollHeight - window.innerHeight;
        if (progress) progress.style.transform = `scaleX(${max > 0 ? Math.min(y / max, 1) : 0})`;
        if (!reduce) floats.forEach((g, i) => (g.style.transform = `translateY(${y * (i % 2 ? -0.05 : 0.04)}px)`));
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  // Reveal sections (and trigger the chart wipe) as they scroll into view.
  useEffect(() => {
    const els = Array.from(document.querySelectorAll(".surge-reveal, .surge-monitor"));
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        }),
      { threshold: 0.12, rootMargin: "0px 0px -6% 0px" }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

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
        <div className="surge-progress" ref={progressRef} aria-hidden />
        <header className="surge-nav">
          <BrandLogo className="text-[21px]" />
          <nav><a href="#how">How it works</a><a href="#report">Sample report</a><Link href="/login">Log in</Link><ThemeToggle/><Link className="surge-nav-cta" href="/signup" {...navCta}>Sign up free <ArrowRight size={15}/></Link></nav>
        </header>

        {deleted && <div className="surge-toast">Your account has been deleted.<button onClick={onDismissDeleted} aria-label="Dismiss">×</button></div>}

        <section className="surge-hero">
          <div className="surge-hero-copy">
            <div className="surge-eyebrow"><Sparkles size={14}/> BUILT FOR SHORT-FORM CREATORS</div>
            <h1>Your next post<br/>shouldn&apos;t lose them <em>here.</em></h1>
            <p>Surge finds the exact moments costing you attention—and tells you what to change <strong>before you post.</strong></p>
            <div className="surge-actions"><a className="surge-primary" href="#upload" {...heroCta}>Analyze my video <ArrowRight size={18}/></a><a className="surge-demo" href="#report"><span><Play size={14}/></span> See a sample report</a></div>
            <div className="surge-trust"><span><Check size={13}/> 3 free analyses</span><span><Tooltip label="Your uploaded video is analyzed privately"><Lock size={13}/></Tooltip> Videos stay private</span><span>No card</span></div>
          </div>

          <div className="surge-monitor" aria-label="Example Surge craft review">
            <div className="surge-monitor-bar"><span className="surge-dots">● ● ●</span><span>surge / craft review</span><span className="surge-live"><b/> Review ready</span></div>
            <div className="surge-monitor-body">
              <div className="surge-video-frame"><div className="surge-video-copy">3 editing tricks<br/><b>nobody tells you</b></div><div className="surge-person"/><div className="surge-timeline"><span>0:09</span><i/></div><label><Tooltip label="AI-estimated craft issue"><Eye size={11}/></Tooltip> Attention risk</label></div>
              <div className="surge-analysis"><div className="surge-analysis-head"><span>Attention risk map <Tooltip label="AI-estimated craft diagnostic, not measured audience retention"><span className="surge-help">?</span></Tooltip></span><b>0:08–0:12</b></div><div className="surge-chart" aria-label="Attention risk drops around 0:09"><div className="surge-chart-line" aria-hidden><i className="seg-one"/><i className="seg-two"/><i className="seg-three"/><i className="seg-four"/><b/></div></div><div className="surge-finding"><span>HIGH RISK · TEXT SCANNABILITY</span><strong>Your caption sits in TikTok&apos;s UI zone.</strong><p>Move it to the upper third and tighten the pause.</p></div><button>Show me the fix <ArrowRight size={15}/></button></div>
            </div>
            <div className="surge-float surge-float-a"><Sparkles size={14}/> AI craft analysis</div><div className="surge-float surge-float-b"><b>+24%</b> clearer hook</div>
          </div>
        </section>

        <div className="surge-platforms surge-reveal"><span>BUILT FOR THE FEEDS YOU CARE ABOUT</span><div><b>♪ <Glitch text="TikTok"/></b><b>◎ <Gradient text="Instagram Reels"/></b></div></div>

        <section className="surge-upload-wrap" id="upload">
          <div className="surge-section-heading surge-reveal"><span>YOUR FIRST WIN</span><h2>See what your viewers see.</h2><p>No dashboards. No guesswork. Drop a draft and get a clear edit list in under a minute.</p></div>
          <form onSubmit={handleSubmit} className="surge-upload-card surge-reveal">
            <div className="surge-platform-tabs"><button type="button" className={platform === "tiktok" ? "active" : ""} onClick={() => setPlatform("tiktok")}>♪ <Glitch text="TikTok"/></button><button type="button" className={platform === "instagram" ? "active" : ""} onClick={() => setPlatform("instagram")}>◎ <Gradient text="Instagram"/></button></div>
            <ReactiveVideoDropzone file={file} onFileSelected={handleFile} selectedDetail={file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB · validation passed` : undefined}/>
            {error && <div className="surge-error">{error}</div>}
            <button type="submit" disabled={processing} className="surge-submit" {...submitBtn}>{file ? "Find my attention leaks" : "Choose a video to continue"}<ArrowRight size={18}/></button>
            <div className="surge-privacy"><Tooltip label="Your upload is encrypted in transit and deleted after analysis"><Lock size={13}/></Tooltip> Encrypted in transit · Automatically deleted after analysis</div>
          </form>
        </section>

        <section className="surge-how" id="how"><div className="surge-section-heading surge-left surge-reveal"><span>HOW IT WORKS</span><h2>From rough cut to<br/><em>ready to post.</em></h2></div><div className="surge-step-grid"><article className="surge-reveal"><b>01</b><div className="surge-step-art"><Upload size={25}/><i/><i/><i/></div><h3>Drop your draft</h3><p>Upload the version sitting in your camera roll. No account needed.</p></article><article className="surge-reveal"><b>02</b><div className="surge-step-art scan"><span>Scanning hook</span><i/></div><h3>Surge reads the edit</h3><p>We review hook, pacing, captions, tension, sync, and ending.</p></article><article className="surge-reveal"><b>03</b><div className="surge-step-art fix"><Check size={25}/><i/><i/><i/></div><h3>Fix what matters</h3><p>Get timestamped changes you can make before your next post.</p></article></div></section>

        <section className="surge-report" id="report"><div className="surge-report-inner"><div className="surge-report-copy surge-reveal"><span>AN ACTUAL SURGE REPORT</span><h2>Feedback that speaks<br/>creator, <em>not corporate.</em></h2><p>Every review turns six craft signals into one clear next experiment.</p><div className="surge-score-list">{SAMPLE_SCORES.slice(0, 4).map((sc) => <div key={sc.label}><span>{sc.label}</span><b>{sc.score}/10</b><i><em style={{ width: `${sc.score * 10}%` }}/></i></div>)}</div></div><div className="surge-report-card surge-reveal"><div><span>BIGGEST ATTENTION LEAK · {SAMPLE_RISK.section}</span><h3>Make the moment easier to read.</h3><p>{SAMPLE_RISK.reason}</p></div><a href="/sample">Explore the full sample report <ArrowRight size={16}/></a></div></div></section>

        <section className="surge-final"><span className="surge-brand-mark large">↯</span><h2 className="surge-reveal">Your better edit is<br/><em>one upload away.</em></h2><p>Find the moment they&apos;ll scroll—before they do.</p><a className="surge-primary" href="#upload" {...finalCta}>Analyze my first video <ArrowRight size={18}/></a><small>Free · no card · under 60 seconds</small></section>
        <footer className="surge-footer"><BrandLogo className="text-[21px]" /><span>Make every second count.</span><div><Link href="/pricing">Pricing</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></div><small>© {new Date().getFullYear()} Surge</small></footer>
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
    return <LandingSkeleton />;
  }

  if (showSplash) {
    return <LandingHero deleted={deleted} onDismissDeleted={() => setDeleted(false)} />;
  }

  return (
    <main className="min-h-screen flex flex-col bg-background">
      <Nav />
      {/* One-time post-signup nudge; self-gates via localStorage. */}
      <ProfileNudgeModal />

      {/* ── Platform toggle ── */}
      <div className="flex justify-center pt-8 px-4">
        <PlatformTabs value={platform} onChange={setPlatform} />
      </div>

      {/* ── Hero ── */}
      <section className="flex flex-col items-center px-4 pt-10 pb-6 text-center">
        <h1 className="text-3xl font-bold text-text-primary tracking-tight">
          Review your next{" "}
          {platform === "tiktok" ? (
            <span className="tiktok-glitch" data-text="TikTok">TikTok</span>
          ) : (
            <span className="gradient-text-instagram">Instagram</span>
          )}{" "}
          video
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
