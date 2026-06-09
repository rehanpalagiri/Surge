"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { analyzeVideo, getProfile, wakeBackend } from "@/lib/api";
import { getToken } from "@/lib/auth";

const NICHES = [
  "Fitness",
  "Comedy",
  "Food",
  "Fashion",
  "Education",
  "Gaming",
  "Lifestyle",
  "Other",
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

const MAX_BYTES = 100 * 1024 * 1024; // 100 MB

function TikTokIcon() {
  // Single connected path tracing the real TikTok note shape:
  //   M33 7        — top-left of stem / outer-left of flag
  //   L50 7        — right along the flag top
  //   Q58 7 58 18  — round the top-right corner of the flag
  //   L58 30       — down the flag's right side
  //   Q58 38 48 38 — round the flag's bottom-right corner
  //   L40 38       — left along flag bottom back to stem width
  //   L40 50       — down stem right side to where it meets the note head
  //   A18 18 0 1 0 33 36 — big CCW arc: sweeps through bottom-left of the ring
  //   Z            — straight line back up the stem left edge to M (33 7)
  //
  // Inner hole (fill-rule evenodd subtracts it):
  //   M22 40  A10 10 0 1 1 22 60  A10 10 0 1 1 22 40 Z
  //   — full circle CW at note-head centre (22,50) r=10

  const d =
    "M33 7 L50 7 Q58 7 58 18 L58 30 Q58 38 48 38 L40 38 L40 50 " +
    "A18 18 0 1 0 33 36 Z " +
    "M22 40 A10 10 0 1 1 22 60 A10 10 0 1 1 22 40 Z";

  return (
    <svg width="72" height="72" viewBox="0 0 72 72" fill="none" xmlns="http://www.w3.org/2000/svg">
      <g transform="translate(-2 2)">
        <path fillRule="evenodd" d={d} fill="#25f4ee" />
      </g>
      <g transform="translate(2 -2)">
        <path fillRule="evenodd" d={d} fill="#fe2c55" />
      </g>
      <path fillRule="evenodd" d={d} style={{ fill: 'var(--tt-note-fill)' }} />
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
  const [niche, setNiche] = useState("Fitness");
  const [caption, setCaption] = useState("");
  const [bio, setBio] = useState("");
  const [loading, setLoading] = useState(false);
  const [waking, setWaking] = useState(false);
  const [tipIndex, setTipIndex] = useState(0);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [mode, setMode] = useState<ModeId>("quick");

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
    setError("");
    setLoading(true);
    setTipIndex(0);

    const interval = setInterval(() => {
      setTipIndex((i) => (i + 1) % TIPS.length);
    }, 5000);

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
      const { id } = await analyzeVideo(file, niche, caption, bio, platform, effectiveMode);
      router.push(`/results/${id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "";
      setError(
        msg.toLowerCase().includes("load failed") || msg.toLowerCase().includes("failed to fetch")
          ? "Couldn't reach the server. Check your connection and try again — if you're on cellular, switching to Wi-Fi can help."
          : msg || "Analysis failed. Please try again."
      );
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
                : "This can take 15–30 seconds"}
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
            p-6 sm:p-10 min-h-[120px]
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
            </>
          )}
        </div>


        {/* ── Niche ────────────────────────────────────────────────────────── */}
        <div>
          <label className="block text-sm font-medium text-text-muted mb-2">
            Content Niche
          </label>
          <select
            value={niche}
            onChange={(e) => setNiche(e.target.value)}
            className="w-full bg-card border border-border rounded-xl px-4 py-3 text-text-primary focus:outline-none focus:border-purple-to focus:ring-1 focus:ring-purple-to appearance-none cursor-pointer"
          >
            {NICHES.map((n) => (
              <option key={n} value={n} className="bg-card">
                {n}
              </option>
            ))}
          </select>
        </div>

        {/* ── Caption ──────────────────────────────────────────────────────── */}
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

        {/* ── Analysis depth ───────────────────────────────────────────────── */}
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

        {error && (
          <div className="bg-danger/10 border border-danger/30 rounded-xl px-4 py-3 text-danger text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={!file || loading}
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
