"use client";

import { useState } from "react";
import { submitFeedback, linkTikTokVideo, apiErrorDetail } from "@/lib/api";

interface FeedbackModalProps {
  analysisId: number;
  platform?: string;
}

export default function FeedbackModal({ analysisId, platform = "tiktok" }: FeedbackModalProps) {
  const isTikTok = platform !== "instagram";
  const [views, setViews] = useState("");
  const [likes, setLikes] = useState("");
  const [link, setLink] = useState("");
  const [manualMode, setManualMode] = useState(!isTikTok);
  const [submitted, setSubmitted] = useState(false);
  const [fetchedStats, setFetchedStats] = useState<{ views: number; likes: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleLinkSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!link.trim()) {
      setError("Paste the link to your posted TikTok first.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const updated = await linkTikTokVideo(analysisId, link.trim());
      setFetchedStats({
        views: updated.actual_views ?? 0,
        likes: updated.actual_likes ?? 0,
      });
      setSubmitted(true);
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Couldn't fetch that video. Try again or enter stats manually."));
    } finally {
      setLoading(false);
    }
  }

  async function handleManualSubmit(e: React.FormEvent) {
    e.preventDefault();
    const viewNum = parseInt(views, 10);
    if (isNaN(viewNum) || viewNum < 0) {
      setError("Please enter a valid view count.");
      return;
    }
    const likeNum = likes.trim() ? parseInt(likes, 10) : undefined;
    if (likeNum !== undefined && (isNaN(likeNum) || likeNum < 0)) {
      setError("Please enter a valid like count.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await submitFeedback(analysisId, viewNum, likeNum);
      setSubmitted(true);
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Failed to submit feedback."));
    } finally {
      setLoading(false);
    }
  }

  if (submitted) {
    return (
      <div className="bg-card border border-border rounded-2xl p-6 text-center">
        <div className="text-3xl mb-2">🎉</div>
        <p className="text-success font-semibold text-lg">
          {fetchedStats ? "Stats synced from TikTok!" : "Thanks for the feedback!"}
        </p>
        {fetchedStats && (
          <p className="text-text-primary text-sm mt-2 font-medium">
            {fetchedStats.views.toLocaleString()} views · {fetchedStats.likes.toLocaleString()} likes
          </p>
        )}
        <p className="text-text-muted text-sm mt-1">
          This helps Surge improve its predictions.
          {fetchedStats && " You can refresh these stats from My Projects as your video grows."}
        </p>
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-2xl p-6">
      <h3 className="text-text-primary font-semibold text-lg mb-1">
        How did your video actually perform?
      </h3>
      <p className="text-text-muted text-sm mb-4">
        {isTikTok && !manualMode
          ? "Paste your posted TikTok link and we'll pull the real numbers — no typing, always current."
          : "Share your actual stats to help improve Surge's predictions."}
      </p>

      {isTikTok && !manualMode ? (
        <form onSubmit={handleLinkSubmit} className="flex flex-col gap-3">
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="url"
              placeholder="https://www.tiktok.com/@you/video/…"
              value={link}
              onChange={(e) => setLink(e.target.value)}
              className="flex-1 bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to focus:ring-1 focus:ring-purple-to"
            />
            <button
              type="submit"
              disabled={loading}
              className="gradient-btn text-white font-semibold px-6 py-2.5 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            >
              {loading ? "Fetching…" : "Fetch my stats"}
            </button>
          </div>
          <button
            type="button"
            onClick={() => { setManualMode(true); setError(""); }}
            className="text-text-muted text-xs hover:text-text-primary self-start underline-offset-2 hover:underline"
          >
            Haven&apos;t posted it yet? Enter stats manually
          </button>
        </form>
      ) : (
        <form onSubmit={handleManualSubmit} className="flex flex-col gap-3">
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="number"
              min="0"
              placeholder="Views (e.g. 15000)"
              value={views}
              onChange={(e) => setViews(e.target.value)}
              className="flex-1 bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to focus:ring-1 focus:ring-purple-to"
            />
            <input
              type="number"
              min="0"
              placeholder="Likes (optional)"
              value={likes}
              onChange={(e) => setLikes(e.target.value)}
              className="flex-1 bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to focus:ring-1 focus:ring-purple-to"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="gradient-btn text-white font-semibold px-6 py-2.5 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Submitting..." : "Submit"}
          </button>
          {isTikTok && (
            <button
              type="button"
              onClick={() => { setManualMode(false); setError(""); }}
              className="text-text-muted text-xs hover:text-text-primary self-start underline-offset-2 hover:underline"
            >
              ← Or paste your TikTok link instead
            </button>
          )}
        </form>
      )}
      {error && <p className="text-danger text-sm mt-2">{error}</p>}
    </div>
  );
}
