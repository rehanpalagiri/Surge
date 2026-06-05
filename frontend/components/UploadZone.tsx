"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { analyzeVideo, getProfile } from "@/lib/api";
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

const TIPS = [
  "Analyzing your hook strength...",
  "Checking trend alignment...",
  "Reviewing pacing and cuts...",
  "Evaluating audio quality...",
  "Scanning caption effectiveness...",
  "Comparing to viral benchmarks...",
  "Generating your performance score...",
];

export default function UploadZone({ platform = "tiktok" }: { platform?: string }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [niche, setNiche] = useState("Fitness");
  const [caption, setCaption] = useState("");
  const [bio, setBio] = useState("");
  const [loading, setLoading] = useState(false);
  const [tipIndex, setTipIndex] = useState(0);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);

  const pName = platform === "instagram" ? "Instagram" : "TikTok";

  // Auto-fill bio from saved profile when platform changes
  useEffect(() => {
    if (!getToken()) return;
    getProfile(platform).then((prof) => {
      if (prof?.bio) setBio(prof.bio);
    }).catch(() => {});
  }, [platform]);

  const handleFile = (f: File) => {
    if (f.size > 100 * 1024 * 1024) {
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
      const { id } = await analyzeVideo(file, niche, caption, bio, platform);
      router.push(`/results/${id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Analysis failed. Please try again.");
      setLoading(false);
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
            <div className="absolute inset-0 flex items-center justify-center text-2xl">🎬</div>
          </div>
          <div className="text-center">
            <p className="text-xl font-bold text-text-primary animate-pulse-slow">
              ViralIQ is analyzing your video...
            </p>
            <p className="text-text-muted text-sm mt-1">This can take 15–30 seconds</p>
          </div>
          <div className="bg-card border border-border rounded-xl px-6 py-3 text-text-muted text-sm animate-pulse">
            {TIPS[tipIndex]}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="w-full max-w-xl mx-auto space-y-4">
        <div
          onDrop={onDrop}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer rounded-2xl border-2 border-dashed transition-all p-10 flex flex-col items-center gap-3 text-center
            ${dragging
              ? "border-purple-to bg-purple-from/10"
              : file
              ? "border-success/60 bg-success/5"
              : "border-border bg-card hover:border-purple-from/50 hover:bg-card/80"
            }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".mp4,.mov,video/mp4,video/quicktime"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
          <div className="text-4xl">{file ? "✅" : "🎥"}</div>
          {file ? (
            <>
              <p className="text-text-primary font-semibold">{file.name}</p>
              <p className="text-text-muted text-sm">{formatSize(file.size)}</p>
              <p className="text-text-muted text-xs">Click to change file</p>
            </>
          ) : (
            <>
              <p className="text-text-primary font-semibold">
                Drop your {pName} video here
              </p>
              <p className="text-text-muted text-sm">
                or click to browse — .mp4 or .mov, max 100MB
              </p>
            </>
          )}
        </div>

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

        <div>
          <label className="block text-sm font-medium text-text-muted mb-2">
            Profile bio{" "}
            <span className="text-text-muted/60 font-normal">(optional)</span>
          </label>
          <input
            type="text"
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            maxLength={500}
            placeholder={`Your ${pName} profile bio`}
            className="w-full bg-card border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to focus:ring-1 focus:ring-purple-to"
          />
        </div>

        {error && (
          <div className="bg-danger/10 border border-danger/30 rounded-xl px-4 py-3 text-danger text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={!file || loading}
          className="w-full gradient-btn text-white font-bold py-4 rounded-xl text-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:scale-[1.01] active:scale-[0.99]"
        >
          {loading ? "Analyzing..." : "Analyze My Video"}
        </button>
      </form>
    </>
  );
}
