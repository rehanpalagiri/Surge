"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { analyzeVideo, getProfile, wakeBackend, getRateLimit, RateLimitStatus } from "@/lib/api";
import { getToken } from "@/lib/auth";

// Quick-tap suggestions — the field itself is free text and the backend maps
// whatever the user types onto its canonical niche list.
const NICHE_SUGGESTIONS = [
  "Fitness",
  "Comedy",
  "Gaming",
  "Food",
  "Fashion",
  "Beauty",
  "Finance",
  "Music",
  "Lifestyle",
  "Tech",
];

const MODES = [
  {
    id: "quick",
    label: "Lite",
    time: "~20 sec",
    desc: "Fast take on the video alone — no benchmarks or history.",
  },
  {
    id: "thinking",
    label: "Thinking",
    time: "~30 sec",
    desc: "Compared against real viral benchmarks for your niche.",
  },
  {
    id: "deep_thinking",
    label: "Deep",
    time: "~60 sec",
    desc: "Benchmarks plus your channel history for a personalized read.",
  },
] as const;

type ModeId = (typeof MODES)[number]["id"];
const MODE_STORAGE_KEY = "surge_mode";

const TIPS = [
  "Analyzing your hook strength...",
  "Checking trend alignment...",
  "Reviewing pacing and cuts...",
  "Evaluating audio quality...",
  "Scanning caption effectiveness...",
  "Comparing to viral benchmarks...",
  "Generating your performance score...",
];

const ANALYSIS_TIME: Record<ModeId, string> = {
  quick: "~20 seconds",
  thinking: "~30 seconds",
  deep_thinking: "~60 seconds",
};

const MAX_BYTES = 100 * 1024 * 1024; // 100 MB

function TikTokIcon() {
  // Official TikTok note glyph (Simple Icons path data, 24×24 grid) — do not
  // hand-edit the path. Three layers: cyan up-left, red down-right (same
  // direction as the .tiktok-glitch text shadow), themed main layer on top.
  const d =
    "M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z";

  return (
    <svg width="72" height="72" viewBox="-2 -2 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d={d} fill="#25f4ee" transform="translate(-0.7 -0.7)" />
      <path d={d} fill="#fe2c55" transform="translate(0.7 0.7)" />
      <path d={d} style={{ fill: "var(--tt-note-fill)" }} />
    </svg>
  );
}

function InstagramIcon() {
  return (
    <svg width="72" height="72" viewBox="0 0 72 72" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="ig-bg" x1="0" y1="72" x2="72" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#fcaf45" />
          <stop offset="35%" stopColor="#fd1d1d" />
          <stop offset="70%" stopColor="#e1306c" />
          <stop offset="100%" stopColor="#833ab4" />
        </linearGradient>
      </defs>
      <rect width="72" height="72" rx="16" fill="url(#ig-bg)" />
      {/* Camera body — inset 10px each side */}
      <rect x="10" y="10" width="52" height="52" rx="14" stroke="white" strokeWidth="3.5" fill="none" />
      {/* Lens */}
      <circle cx="36" cy="37" r="12" stroke="white" strokeWidth="3.5" fill="none" />
      {/* Viewfinder dot — top-right of camera body */}
      <circle cx="51" cy="21" r="3.5" fill="white" />
    </svg>
  );
}

interface Props {
  platform?: string;
  /** Pre-populate with a file (e.g. from the Web Share Target) */
  initialFile?: File | null;
}

export default function UploadZone({ platform = "tiktok", initialFile = null }: Props) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [niche, setNiche] = useState("");
  const [caption, setCaption] = useState("");
  const [bio, setBio] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [waking, setWaking] = useState(false);
  const [tipIndex, setTipIndex] = useState(0);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [mode, setMode] = useState<ModeId>("quick");
  const [rateLimit, setRateLimit] = useState<RateLimitStatus | null>(null);

  const pName = platform === "instagram" ? "Instagram" : "TikTok";
  const textGradient = platform === "instagram" ? "gradient-text-instagram" : "tiktok-glitch-sm";

  // Detect auth + restore the last-used mode (client-only to avoid hydration mismatch).
  useEffect(() => {
    const authed = !!getToken();
    setLoggedIn(authed);
    if (!authed) {
      setMode("quick");
      return;
    }
    const saved = localStorage.getItem(MODE_STORAGE_KEY);
    if (saved && MODES.some((m) => m.id === saved)) {
      setMode(saved as ModeId);
    } else {
      setMode("thinking"); // sensible default for logged-in creators
    }
    getRateLimit().then(setRateLimit).catch(() => {});
  }, []);

  const pickMode = (m: ModeId) => {
    setMode(m);
    try {
      localStorage.setItem(MODE_STORAGE_KEY, m);
    } catch {
      // ignore storage failures (private mode etc.)
    }
  };

  // Accept a file pre-populated by the share page
  useEffect(() => {
    if (!initialFile) return;
    if (initialFile.size > MAX_BYTES) {
      setError("File must be under 100MB.");
      return;
    }
    setError("");
    setFile(initialFile);
  }, [initialFile]);

  // Auto-fill bio from saved profile when platform changes
  useEffect(() => {
    if (!getToken()) return;
    getProfile(platform)
      .then((prof) => {
        if (prof?.bio) setBio(prof.bio);
      })
      .catch(() => {});
  }, [platform]);

  const handleFile = (f: File) => {
    if (f.size > MAX_BYTES) {
      setError("File must be under 100MB.");
      return;
    }
    setError("");
    setFile(f);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []);

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  };

  const onDragLeave = () => setDragging(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    // When advanced settings are open and niche is empty, require it.
    // When collapsed, default to "General" so the user can analyze without filling it in.
    if (showAdvanced && !niche.trim()) {
      setError("Tell us your content niche — type it or tap a suggestion below.");
      return;
    }
    const effectiveNiche = niche.trim() || "General";
    setError("");
    setLoading(true);
    setTipIndex(0);

    const interval = setInterval(() => {
      setTipIndex((i) => (i + 1) % TIPS.length);
    }, 4000);

    try {
      // Ping the backend with a tiny request first and wait for it to respond.
      // Render's free tier can take 20-60s to wake from a cold start — if that
      // wake-up happens mid-upload (a big multipart POST), mobile Safari often
      // drops the connection and throws a generic "Load failed". Warming it up
      // first keeps the heavy upload itself fast and reliable.
      setWaking(true);
      const awake = await wakeBackend();
      setWaking(false);
      if (!awake) throw new Error("load failed");

      const effectiveMode = loggedIn ? mode : "quick";
      const { id } = await analyzeVideo(file, effectiveNiche, caption, bio, platform, effectiveMode);
      getRateLimit().then(setRateLimit).catch(() => {});
      router.push(`/results/${id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("429")) {
        getRateLimit().then(setRateLimit).catch(() => {});
        setError(msg.replace(/^API error 429: /, "") || "Upload limit reached. Link a posted video to earn more credits.");
      } else {
        setError(
          msg.toLowerCase().includes("load failed") || msg.toLowerCase().includes("failed to fetch")
            ? "Couldn't reach the server. Check your connection and try again — if you're on cellular, switching to Wi-Fi can help."
            : msg || "Analysis failed. Please try again."
        );
      }
      setLoading(false);
      setWaking(false);
    } finally {
      clearInterval(interval);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <>
      {loading && (
        <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col items-center justify-center gap-6 px-4">
          <div className="relative">
            <div className="w-20 h-20 rounded-full border-4 border-purple-from/20 border-t-purple-to animate-spin" />
            <div className="absolute inset-0 flex items-center justify-center text-2xl">
              🎬
            </div>
          </div>
          <div className="text-center">
            <p className="text-xl font-bold text-text-primary animate-pulse-slow">
              {waking ? "Waking up the server…" : "Surge is analyzing your video..."}
            </p>
            <p className="text-text-muted text-sm mt-1">
              {waking
                ? "First request after a quiet period can take up to a minute — hang tight"
                : `This usually takes ${ANALYSIS_TIME[loggedIn ? mode : "quick"]}`}
            </p>
          </div>
          <div className="bg-card border border-border rounded-xl px-6 py-3 text-text-muted text-sm animate-pulse">
            {waking ? "Connecting to Surge's analysis engine…" : TIPS[tipIndex]}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="w-full max-w-xl mx-auto space-y-4">
        {/* ── Drop / tap zone ──────────────────────────────────────────────── */}
        <div
          onDrop={onDrop}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer rounded-2xl border-2 border-dashed transition-all
            p-8 sm:p-12 min-h-[220px]
            flex flex-col items-center justify-center gap-3 text-center
            ${
              dragging
                ? "border-purple-to bg-purple-from/10"
                : file
                ? "border-success/60 bg-success/5"
                : "border-border bg-card hover:border-purple-from/50 hover:bg-card/80"
            }`}
        >
          {/* accept="video/*" — on iOS this shows "Photo Library" as primary option.
              No `capture` attribute so camera isn't forced. */}
          <input
            ref={inputRef}
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
          {file ? (
            <>
              <div className="text-4xl">✅</div>
              <p className="text-text-primary font-semibold">{file.name}</p>
              <p className="text-text-muted text-sm">{formatSize(file.size)}</p>
              <p className="text-text-muted text-xs">Tap to change file</p>
            </>
          ) : (
            <>
              {platform === "instagram" ? <InstagramIcon /> : <TikTokIcon />}
              {/* Mobile copy */}
              <p className="text-xl font-bold text-white sm:hidden">
                Tap to add your{" "}
                <span className={textGradient}>{pName}</span>{" "}
                video
              </p>
              {/* Desktop copy */}
              <p className="text-xl font-bold text-white hidden sm:block">
                Drop your{" "}
                <span className={textGradient}>{pName}</span>{" "}
                video here
              </p>
              <p className="text-white/50 text-sm">
                .mp4 or .mov · up to 100MB
              </p>
              <p className="text-white/30 text-xs">
                iPhone: trim in Photos first to shrink large files
              </p>
            </>
          )}
        </div>


        {/* ── Advanced settings toggle ─────────────────────────────────── */}
        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="flex items-center gap-1.5 text-text-muted text-sm hover:text-text-primary transition-colors mx-auto"
          >
            <span className={`transition-transform duration-200 ${showAdvanced ? "rotate-180" : ""}`}>
              ▾
            </span>
            Advanced settings
            {(niche || caption) && !showAdvanced && (
              <span className="ml-1 w-1.5 h-1.5 rounded-full bg-purple-to inline-block" title="Custom settings active" />
            )}
          </button>
        </div>

        {showAdvanced && (
          <>
            {/* ── Niche ─────────────────────────────────────────────────── */}
            <div>
              <label className="block text-sm font-medium text-text-muted mb-2">
                Content Niche
                <span className="text-text-muted/50 font-normal ml-1">(defaults to General)</span>
              </label>
              <input
                type="text"
                value={niche}
                onChange={(e) => setNiche(e.target.value)}
                maxLength={80}
                placeholder='e.g. "Dark humor skits", "Calisthenics", "Day trading"…'
                className="w-full bg-card border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to focus:ring-1 focus:ring-purple-to"
              />
              <div className="flex flex-wrap gap-2 mt-2">
                {NICHE_SUGGESTIONS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setNiche(n)}
                    className={`px-3 py-1.5 rounded-full border text-xs font-medium transition-all ${
                      niche === n
                        ? "border-purple-to bg-purple-from/10 text-text-primary"
                        : "border-border bg-card text-text-muted hover:border-purple-from/50 hover:text-text-primary"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>

            {/* ── Caption ───────────────────────────────────────────────── */}
            <div>
              <label className="block text-sm font-medium text-text-muted mb-2">
                Caption{" "}
                <span className="text-text-muted/60 font-normal">(optional)</span>
              </label>
              <textarea
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                rows={2}
                maxLength={2200}
                placeholder="The caption you plan to post with this video, including hashtags…"
                className="w-full bg-card border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to focus:ring-1 focus:ring-purple-to resize-none"
              />
            </div>

            {/* ── Analysis depth ────────────────────────────────────────── */}
            {loggedIn ? (
              <div>
                <label className="block text-sm font-medium text-text-muted mb-2">
                  Analysis depth
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {MODES.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => pickMode(m.id)}
                      aria-pressed={mode === m.id}
                      className={`rounded-xl border px-3 py-2.5 text-left transition-all ${
                        mode === m.id
                          ? "border-purple-to bg-purple-from/10"
                          : "border-border bg-card hover:border-purple-from/50"
                      }`}
                    >
                      <span className="block text-sm font-semibold text-text-primary">
                        {m.label}
                      </span>
                      <span className="block text-[11px] text-text-muted leading-tight mt-0.5">
                        {m.time}
                      </span>
                    </button>
                  ))}
                </div>
                {MODES.find((m) => m.id === mode) && (
                  <p className="text-text-muted/70 text-xs mt-2">
                    {MODES.find((m) => m.id === mode)!.desc}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-text-muted text-xs text-center px-2">
                Running a <span className="text-text-primary font-medium">Quick</span> analysis.{" "}
                <Link href="/login" className="text-purple-to hover:underline">
                  Sign in
                </Link>{" "}
                for Thinking &amp; Deep modes.
              </p>
            )}
          </>
        )}

        {/* ── Rate limit bar (logged-in only) ─────────────────────────────── */}
        {loggedIn && rateLimit && (
          <div className="bg-surface border border-border rounded-xl px-4 py-3 space-y-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="text-text-muted">
                {rateLimit.remaining} of {rateLimit.effective_limit} analyses left
                <span className="text-text-muted/50"> · {rateLimit.window_hours}h window</span>
              </span>
              {rateLimit.bonus > 0 && (
                <span className="text-emerald-400 font-medium">+{rateLimit.bonus} link bonus</span>
              )}
            </div>
            <div className="w-full h-1 bg-border rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  rateLimit.remaining === 0 ? "bg-danger" :
                  rateLimit.remaining <= 3 ? "bg-yellow-400" : "bg-purple-to"
                }`}
                style={{ width: `${Math.round((rateLimit.used / rateLimit.effective_limit) * 100)}%` }}
              />
            </div>
            {rateLimit.remaining === 0 ? (
              <p className="text-danger text-[11px]">
                Limit reached.{" "}
                {rateLimit.bonus < 10 && "Link a posted video below to earn +1 credit. "}
                {rateLimit.resets_at && `Resets ${new Date(rateLimit.resets_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.`}
              </p>
            ) : rateLimit.bonus < 10 ? (
              <p className="text-text-muted/60 text-[11px]">
                Link a posted video on your results page to earn +1 credit (up to +10 total).
              </p>
            ) : null}
          </div>
        )}

        {error && (
          <div className="bg-danger/10 border border-danger/30 rounded-xl px-4 py-3 text-danger text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={!file || loading || (rateLimit?.remaining === 0)}
          className={`w-full ${
            platform === "instagram" ? "gradient-btn-instagram" : "gradient-btn"
          } text-white font-bold py-4 rounded-xl text-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:scale-[1.01] active:scale-[0.99]`}
        >
          {loading ? "Analyzing..." : "Analyze My Video"}
        </button>
      </form>
    </>
  );
}
