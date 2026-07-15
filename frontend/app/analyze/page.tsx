"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Lock } from "lucide-react";
import Nav from "@/components/Nav";
import PlatformTabs, { type Platform } from "@/components/PlatformTabs";
import ReactiveVideoDropzone from "@/components/ReactiveVideoDropzone";
import { AnalysisOverlay } from "@/components/AnalysisProgress";
import { Tooltip } from "@/components/Tooltip";
import { analyzeVideo, wakeBackend } from "@/lib/api";
import { isAllowedVideoFile } from "@/lib/videoValidation";
import { track } from "@vercel/analytics";

const MAX_BYTES = 100 * 1024 * 1024;
const PROCESSING_STEPS = [
  "Analyzing the first-3-second hook…",
  "Scanning for on-screen text collisions…",
  "Measuring cut rhythm and pacing…",
  "Checking audio-visual sync and the ending…",
  "Writing your craft review…",
];

function formatBadRequestMessage(message: string) {
  const detail = message.replace(/^API error 400:\s*/, "");
  try {
    const parsed = JSON.parse(detail);
    if (typeof parsed?.detail === "string") return parsed.detail;
  } catch {
    // Plain-text API errors are already suitable for display.
  }
  return detail || "Analysis failed. Please try again.";
}

export default function AnalyzePage() {
  const router = useRouter();
  const [platform, setPlatform] = useState<Platform>("tiktok");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [processing, setProcessing] = useState(false);

  const handleFile = async (selected: File) => {
    setFile(null);
    setError("");
    if (!isAllowedVideoFile(selected)) {
      setError("Please upload a supported video file (MP4, MOV, WEBM, AVI & more).");
      return;
    }
    if (selected.size > MAX_BYTES) {
      setError("Your video is too large. Maximum size is 100 MB — try exporting at 720p from your camera app.");
      return;
    }

    const duration = await new Promise<number>((resolve) => {
      const video = document.createElement("video");
      video.preload = "metadata";
      const url = URL.createObjectURL(selected);
      video.onloadedmetadata = () => { URL.revokeObjectURL(url); resolve(video.duration); };
      video.onerror = () => { URL.revokeObjectURL(url); resolve(0); };
      video.src = url;
    });
    if (duration > 600) {
      setError("Your video is over 10 minutes. Please trim it before uploading.");
      return;
    }
    setFile(selected);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) {
      setError("Upload a video to get started — MP4, MOV, WEBM, AVI & more.");
      return;
    }

    setError("");
    setProcessing(true);
    track("upload_started", { platform, niche_count: 0, logged_in: false });
    try {
      await wakeBackend();
      const { id } = await analyzeVideo(file, "", "", "", platform, "", "");
      track("analysis_complete", { platform, mode: "direct" });
      router.push(`/results/${id}`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "";
      track("upload_error", { error_type: message.includes("429") ? "rate_limit" : message.includes("400") ? "validation" : "other" });
      setProcessing(false);
      if (message.includes("429")) setError("You've used your free analyses for today. Sign up free to get more.");
      else if (message.includes("400")) setError(formatBadRequestMessage(message));
      else setError(message || "Analysis failed. Please try again.");
    }
  };

  if (processing) {
    return <AnalysisOverlay active steps={PROCESSING_STEPS} />;
  }

  return (
    <main className="min-h-screen bg-background">
      <Nav />
      <section className="mx-auto w-full max-w-3xl px-4 py-14 sm:py-20">
        <div className="mx-auto mb-8 max-w-xl text-center">
          <p className="text-xs font-bold tracking-[0.18em] text-accent">YOUR NEXT REVIEW</p>
          <h1 className="mt-3 text-3xl font-bold text-text-primary sm:text-4xl">Analyze your video</h1>
          <p className="mt-3 text-sm leading-relaxed text-text-muted sm:text-base">Upload a draft and get a focused craft review before you post.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 rounded-3xl border border-border bg-card p-4 shadow-xl sm:p-6">
          <div className="flex justify-center">
            <PlatformTabs value={platform} onChange={setPlatform} />
          </div>
          <ReactiveVideoDropzone
            file={file}
            onFileSelected={handleFile}
            selectedDetail={file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB · validation passed` : undefined}
          />
          {error && <div className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</div>}
          <button type="submit" disabled={processing} className="gradient-btn flex w-full items-center justify-center gap-2 rounded-xl py-4 text-base font-bold text-white disabled:cursor-not-allowed disabled:opacity-50">
            {file ? "Review my video" : "Choose a video to continue"} <ArrowRight size={18} />
          </button>
          <p className="flex items-center justify-center gap-1.5 text-center text-xs text-text-muted"><Tooltip label="Your uploaded video is analyzed privately"><Lock size={13} /></Tooltip> Encrypted in transit · Automatically deleted after analysis</p>
        </form>
      </section>
    </main>
  );
}
