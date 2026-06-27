"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FileVideo2 } from "lucide-react";
import { getProfile, wakeBackend, getRateLimit, RateLimitStatus, getPresignedUploadUrl, uploadFileToR2, analyzeFromR2, getAnalysisStatus } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { isAllowedVideoFile, uploadContentTypeFor } from "@/lib/videoValidation";
import { AnalysisProgress } from "@/components/AnalysisProgress";
import { track } from "@vercel/analytics";
import ReactiveVideoDropzone from "@/components/ReactiveVideoDropzone";
import NichePicker from "@/components/NichePicker";


const TIPS = [
  "Analyzing your hook strength...",
  "Checking trend alignment...",
  "Reviewing pacing and cuts...",
  "Evaluating audio quality...",
  "Scanning caption effectiveness...",
  "Comparing observable craft patterns...",
  "Generating your craft assessment...",
];

const MAX_DURATION_SECS = 10 * 60;          // 10 minutes
const MAX_BYTES        = 100 * 1024 * 1024; // 100 MB hard limit to backend
const TARGET_BYTES     = 95  * 1024 * 1024; // compress to < 95 MB
const GUEST_LIMIT      = 5;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtDuration(secs: number) {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function getVideoDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const video = document.createElement("video");
    video.preload = "metadata";
    const url = URL.createObjectURL(file);
    video.onloadedmetadata = () => { URL.revokeObjectURL(url); resolve(video.duration); };
    video.onerror = () => { URL.revokeObjectURL(url); reject(new Error("unreadable")); };
    video.src = url;
  });
}

function readGuestCount(): number {
  try {
    const today = new Date().toISOString().slice(0, 10);
    const savedDate  = localStorage.getItem("surge_guest_date");
    const savedCount = parseInt(localStorage.getItem("surge_guest_count") ?? "0", 10);
    return savedDate === today ? (isNaN(savedCount) ? 0 : savedCount) : 0;
  } catch { return 0; }
}

function writeGuestCount(count: number) {
  try {
    const today = new Date().toISOString().slice(0, 10);
    localStorage.setItem("surge_guest_date",  today);
    localStorage.setItem("surge_guest_count", String(count));
  } catch { /* ignore */ }
}

// Singleton — load WASM once per session, reuse after
let ffmpegInstance: import("@ffmpeg/ffmpeg").FFmpeg | null = null;

async function getFFmpeg() {
  if (ffmpegInstance) return ffmpegInstance;
  const { FFmpeg } = await import("@ffmpeg/ffmpeg");
  const { toBlobURL } = await import("@ffmpeg/util");
  const ff = new FFmpeg();
  const base = "https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.12.6/dist/umd";
  await ff.load({
    coreURL: await toBlobURL(`${base}/ffmpeg-core.js`,   "text/javascript"),
    wasmURL: await toBlobURL(`${base}/ffmpeg-core.wasm`, "application/wasm"),
  });
  ffmpegInstance = ff;
  return ff;
}

async function compressVideo(
  file: File,
  onPhase: (phase: string) => void,
  onProgress: (pct: number) => void,
): Promise<File> {
  onPhase("Loading compression engine (~30 MB)…");
  const { fetchFile } = await import("@ffmpeg/util");
  const ff = await getFFmpeg();

  onPhase("Writing video to memory…");
  await ff.writeFile("input.mp4", await fetchFile(file));

  ff.on("progress", ({ progress }) => onProgress(Math.min(99, Math.round(progress * 100))));

  // Pass 1 — 720p @ 1.2 Mbps (~90 MB for 10 min)
  onPhase("Compressing to 720p…");
  await ff.exec([
    "-i", "input.mp4",
    "-vf", "scale=-2:'min(720,ih)'",
    "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1200k",
    "-c:a", "aac", "-b:a", "128k",
    "-movflags", "+faststart",
    "-y", "output.mp4",
  ]);

  const raw1 = await ff.readFile("output.mp4");
  const buf1 = raw1 instanceof Uint8Array ? raw1.buffer.slice(0) as ArrayBuffer : raw1;
  if ((buf1 as ArrayBuffer).byteLength <= TARGET_BYTES) {
    await ff.deleteFile("input.mp4");
    await ff.deleteFile("output.mp4");
    onProgress(100);
    return new File([buf1], sanitizeName(file.name), { type: "video/mp4" });
  }

  // Pass 2 — 480p @ 800 kbps
  onPhase("Still large — compressing to 480p…");
  await ff.exec([
    "-i", "input.mp4",
    "-vf", "scale=-2:'min(480,ih)'",
    "-c:v", "libx264", "-preset", "veryfast", "-b:v", "800k",
    "-c:a", "aac", "-b:a", "96k",
    "-movflags", "+faststart",
    "-y", "output2.mp4",
  ]);

  const raw2 = await ff.readFile("output2.mp4");
  const buf2 = raw2 instanceof Uint8Array ? raw2.buffer.slice(0) as ArrayBuffer : raw2;
  await ff.deleteFile("input.mp4");
  await ff.deleteFile("output.mp4");
  await ff.deleteFile("output2.mp4");
  onProgress(100);
  return new File([buf2], sanitizeName(file.name), { type: "video/mp4" });
}

function sanitizeName(name: string) {
  return name.replace(/\.[^.]+$/, ".mp4");
}

// ─── Component ───────────────────────────────────────────────────────────────

interface Props {
  platform?: string;
  initialFile?: File | null;
  parentId?: number;
  initialNiches?: string[];
}

export default function UploadZone({ platform = "tiktok", initialFile = null, parentId, initialNiches }: Props) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [niches, setNiches] = useState<string[]>(initialNiches ?? []);  // up to 2; first = primary, second = blend
  const [showRubricHint, setShowRubricHint] = useState(Boolean(initialNiches?.length));
  const [caption, setCaption] = useState("");
  const [bio, setBio] = useState("");
  const [loading, setLoading] = useState(false);
  const [waking, setWaking] = useState(false);
  const [error, setError] = useState("");
  const [loggedIn, setLoggedIn] = useState(false);
  const [rateLimit, setRateLimit] = useState<RateLimitStatus | null>(null);
  const [guestCount, setGuestCount] = useState(0);

  // Compression state
  const [compressing, setCompressing] = useState(false);
  const [compressPhase, setCompressPhase] = useState("");
  const [compressProgress, setCompressProgress] = useState(0);

  // Upload state. The "analyzing" phase is handled by <AnalysisProgress>, which
  // owns the percentage, the rotating steps, and the late skeleton reveal.
  const [uploadPhase, setUploadPhase] = useState<"idle" | "uploading" | "analyzing">("idle");
  const [uploadProgress, setUploadProgress] = useState(0);

  useEffect(() => {
    const authed = !!getToken();
    setLoggedIn(authed);
    if (!authed) {
      setGuestCount(readGuestCount());
      return;
    }
    getRateLimit().then(setRateLimit).catch(() => {});
  }, []);

  useEffect(() => {
    if (!initialFile) return;
    processFile(initialFile);
  }, [initialFile]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!getToken()) return;
    getProfile(platform).then((prof) => { if (prof?.bio) setBio(prof.bio); }).catch(() => {});
  }, [platform]);

  // ── File acceptance pipeline ──────────────────────────────────────────────

  async function processFile(f: File) {
    setError("");

    if (!isAllowedVideoFile(f)) {
      setError("Please upload a supported video file (MP4, MOV, WEBM, AVI & more).");
      return;
    }

    // 1. Duration check
    let duration = 0;
    try { duration = await getVideoDuration(f); } catch { /* fall through */ }

    if (duration > MAX_DURATION_SECS) {
      setError(
        `Your video is ${fmtDuration(duration)} long — the maximum is 10 minutes. ` +
        `Trim it in your camera app or a free editor before uploading.`
      );
      return;
    }

    // 2. Under 100MB — accept immediately
    if (f.size <= MAX_BYTES) {
      setFile(f);
      return;
    }

    // 3. Over 100MB — compress client-side
    setCompressing(true);
    setCompressProgress(0);
    setCompressPhase("Starting…");

    try {
      const compressed = await compressVideo(
        f,
        (phase) => setCompressPhase(phase),
        (pct)   => setCompressProgress(pct),
      );

      if (compressed.size > MAX_BYTES) {
        setError(
          `Even after compression this video is ${fmtSize(compressed.size)} — ` +
          `try trimming it to under 8 minutes, or export at 720p from your camera app.`
        );
        return;
      }

      setFile(compressed);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      setError(
        msg.includes("SharedArrayBuffer") || msg.includes("cross-origin")
          ? "Compression not supported in this browser. Export your video at 720p or lower and try again."
          : `Compression failed: ${msg || "unknown error"}. Try exporting at 720p from your camera app.`
      );
    } finally {
      setCompressing(false);
    }
  }

  const handleFile = (f: File) => processFile(f);

  // ── Submit ────────────────────────────────────────────────────────────────

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setError("");
    track("upload_started", { platform, niche_count: niches.length, logged_in: loggedIn });
    setLoading(true);
    setUploadPhase("idle");
    setUploadProgress(0);

    try {
      setWaking(true);
      const awake = await wakeBackend();
      setWaking(false);
      if (!awake) throw new Error("load failed");

      // Phase 1: get presigned upload URL
      const uploadContentType = uploadContentTypeFor(file);
      const { upload_url, key } = await getPresignedUploadUrl(file.name, uploadContentType);

      // Phase 2: upload directly to R2
      setUploadPhase("uploading");
      await uploadFileToR2(upload_url, file, setUploadProgress, uploadContentType);

      // Phase 3: trigger async analysis
      setUploadPhase("analyzing");

      const { id } = await analyzeFromR2(
        key,
        niches[0] ?? "",
        caption,
        bio,
        platform,
        niches[1] ?? "",
        parentId,
      );

      // Track guest usage immediately after analysis is accepted
      if (!loggedIn) {
        const newCount = guestCount + 1;
        writeGuestCount(newCount);
        setGuestCount(newCount);
      } else {
        getRateLimit().then(setRateLimit).catch(() => {});
      }

      // Phase 4: poll until Gemini finishes. Ramped backoff instead of a flat
      // 3s: the first checks come fast (≈0.8s) so a quick review returns almost
      // immediately, then the interval eases out to 3s to spare the API. This
      // removes up to ~3s of dead-time at the end of every analysis.
      const deadline = Date.now() + 5 * 60 * 1000;
      let delay = 800;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, delay));
        const { status } = await getAnalysisStatus(id);
        if (status === "complete") {
          track("analysis_complete", { platform, mode: "r2_async" });
          router.push(`/results/${id}`);
          return;
        }
        if (status === "error") {
          throw new Error("Analysis failed. Please try again.");
        }
        delay = Math.min(3000, Math.round(delay * 1.3));
      }
      throw new Error("Analysis timed out. Please try again.");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("429")) {
        if (loggedIn) getRateLimit().then(setRateLimit).catch(() => {});
        setError(msg.replace(/^API error 429: /, "") || "Upload limit reached. Link a posted video to earn more credits.");
      } else {
        setError(
          msg.toLowerCase().includes("load failed") || msg.toLowerCase().includes("failed to fetch")
            ? "Couldn't reach the server. Check your connection and try again — if you're on cellular, switching to Wi-Fi can help."
            : msg || "Analysis failed. Please try again."
        );
      }
      track("upload_error", { error_type: msg.includes("429") ? "rate_limit" : "other" });
      setLoading(false);
      setWaking(false);
      setUploadPhase("idle");
    }
  };

  const guestLimitReached = !loggedIn && guestCount >= GUEST_LIMIT;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      {/* ── Analysis loading overlay ── */}
      {loading && (
        <div
          className="fixed inset-0 z-50 bg-zinc-950/95 backdrop-blur-sm overflow-y-auto px-4 py-8 sm:py-10"
          role="dialog"
          aria-modal="true"
          aria-busy="true"
          aria-label={uploadPhase === "uploading" ? "Uploading your video" : "Preparing your craft review"}
        >
          <div className="mx-auto flex w-full max-w-3xl flex-col items-center gap-5">
          {uploadPhase === "uploading" ? (
            <>
              <div className="text-center space-y-1">
                <p className="text-xl font-bold text-white">Uploading your video...</p>
                <p className="text-zinc-500 text-sm">Going straight to the cloud — no server in the way</p>
              </div>
              <div className="reactive-transfer-card w-full max-w-xl space-y-4" role="status">
                <div className="relative z-10 flex items-center gap-3 text-left">
                  <div className="dropzone-file-icon">
                    <FileVideo2 className="h-6 w-6" strokeWidth={1.6} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-white">{file?.name ?? "Video file"}</p>
                    <p className="mt-0.5 text-xs text-zinc-500">Secure direct upload</p>
                  </div>
                  <span className="text-sm font-bold tabular-nums text-purple-300">{uploadProgress}%</span>
                </div>
                <div className="transfer-progress-track relative z-10">
                  <div
                    className="transfer-progress-fill"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <div className="relative z-10 flex items-center justify-between text-[11px] text-zinc-500">
                  <span>Keep this tab open</span>
                  <span>{uploadProgress < 100 ? "Transferring…" : "Upload complete"}</span>
                </div>
              </div>
            </>
          ) : waking ? (
            <div className="flex w-full flex-col items-center gap-6 py-6 text-center">
              <div className="space-y-1.5">
                <p className="text-xl font-bold text-white">Waking up the server…</p>
                <p className="text-zinc-500 text-sm">First request after a quiet period can take up to 20 seconds</p>
              </div>
              <div className="h-2 w-full max-w-sm overflow-hidden rounded-full bg-zinc-800">
                <div className="h-full w-1/4 rounded-full bg-purple-500 animate-pulse" />
              </div>
            </div>
          ) : (
            /* Percentage meter → late skeleton reveal, all owned by one component. */
            <AnalysisProgress active steps={TIPS} />
          )}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="w-full max-w-xl mx-auto space-y-5">

        {/* ── Update banner ── */}
        {parentId != null && (
          <div className="flex items-center gap-2 bg-purple-500/10 border border-purple-500/30 rounded-xl px-4 py-3">
            <p className="text-purple-300 text-sm font-medium">
              Updating this project — compare the same craft dimensions
            </p>
          </div>
        )}

        {/* ── Upload / Compression Zone ── */}
        {compressing ? (
          <div className="reactive-transfer-card min-h-[180px] sm:min-h-[220px] flex flex-col items-center justify-center gap-4 text-center">
            <div className="text-3xl">⚙️</div>
            <div className="space-y-1">
              <p className="text-white font-semibold text-sm">Compressing your video...</p>
              <p className="text-zinc-500 text-xs">This may take 30–90 seconds — please keep this tab open</p>
            </div>
            <div className="w-full max-w-xs space-y-2.5">
              <div className="transfer-progress-track">
                <div
                  className="transfer-progress-fill"
                  style={{ width: `${compressProgress}%` }}
                />
              </div>
              <p className="text-zinc-400 text-xs text-center">{compressPhase}</p>
            </div>
          </div>
        ) : (
          <ReactiveVideoDropzone
            file={file}
            onFileSelected={handleFile}
            selectedDetail={file ? (
              <>
                {fmtSize(file.size)}
              </>
            ) : undefined}
          />
        )}

        {/* ── Optional rubric hint ── */}
        <div className="mb-6 rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3">
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

        {/* ── Caption ── */}
        <div>
          <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
            Caption{" "}
            <span className="text-zinc-600 font-normal normal-case tracking-normal">— optional, improves accuracy</span>
          </label>
          <textarea
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            rows={2}
            maxLength={2200}
            placeholder="The caption you plan to post with this video, including hashtags…"
            className="w-full bg-zinc-900 border border-zinc-700 rounded-xl px-4 py-3 text-white placeholder:text-zinc-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-colors text-sm resize-none"
          />
        </div>

        {/* ── Sign-in nudge for guests (replaces mode picker) ── */}
        {!loggedIn && (
          <p className="text-zinc-500 text-xs text-center px-2">
            <Link
              href="/signup"
              className="text-purple-400 hover:text-purple-300 hover:underline transition-colors"
            >
              Sign in
            </Link>{" "}
            for deeper AI analysis.
          </p>
        )}

        {/* ── Rate limit bar (logged-in only) ── */}
        {loggedIn && rateLimit && (
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl px-4 py-3 space-y-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="text-zinc-400">
                {rateLimit.remaining} of {rateLimit.effective_limit} analyses left
                <span className="text-zinc-600"> · {rateLimit.window_hours}h window</span>
              </span>
              {rateLimit.bonus > 0 && (
                <span className="text-emerald-400 font-medium">+{rateLimit.bonus} link bonus</span>
              )}
            </div>
            <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  rateLimit.remaining === 0 ? "bg-red-500" :
                  rateLimit.remaining <= 3 ? "bg-yellow-400" : "bg-purple-500"
                }`}
                style={{ width: `${Math.round((rateLimit.used / rateLimit.effective_limit) * 100)}%` }}
              />
            </div>
            {rateLimit.remaining === 0 ? (
              <p className="text-red-400 text-[11px]">
                Limit reached.{" "}
                {rateLimit.bonus < 10 && "Link a posted video below to earn +1 credit. "}
                {rateLimit.resets_at && `Resets ${new Date(rateLimit.resets_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.`}
              </p>
            ) : rateLimit.bonus < 10 ? (
              <p className="text-zinc-600 text-[11px]">
                Link a posted video on your results page to earn +1 credit (up to +10 total).
              </p>
            ) : null}
          </div>
        )}

        {/* ── Error ── */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* ── Submit ── */}
        <button
          type="submit"
          disabled={!file || loading || compressing || guestLimitReached || (rateLimit?.remaining === 0)}
          className="gradient-btn w-full text-white font-bold py-4 rounded-xl text-lg
            disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:shadow-none"
        >
          {loading ? "Analyzing..." : compressing ? "Compressing video…" : parentId != null ? "Update Project" : "Analyze My Video"}
        </button>

        {/* ── Guest counter ── */}
        {!loggedIn && (
          guestLimitReached ? (
            <div className="text-center space-y-3 pt-1">
              <p className="text-zinc-400 text-sm">
                You&apos;ve used your {GUEST_LIMIT} free analyses today.
              </p>
              <Link
                href="/signup"
                className="gradient-btn inline-block text-white font-semibold px-6 py-2.5 rounded-xl text-sm"
              >
                Sign up free for more
              </Link>
            </div>
          ) : guestCount > 0 ? (
            <p className="text-zinc-400 text-xs text-center">
              {guestCount} of {GUEST_LIMIT} free analyses used today
            </p>
          ) : null
        )}
      </form>
    </>
  );
}
