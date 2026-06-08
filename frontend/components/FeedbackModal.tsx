"use client";

import { useState } from "react";
import { submitFeedback } from "@/lib/api";

interface FeedbackModalProps {
  analysisId: number;
}

export default function FeedbackModal({ analysisId }: FeedbackModalProps) {
  const [views, setViews] = useState("");
  const [likes, setLikes] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
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
      setError(err instanceof Error ? err.message : "Failed to submit feedback.");
    } finally {
      setLoading(false);
    }
  }

  if (submitted) {
    return (
      <div className="bg-card border border-border rounded-2xl p-6 text-center">
        <div className="text-3xl mb-2">🎉</div>
        <p className="text-success font-semibold text-lg">Thanks for the feedback!</p>
        <p className="text-text-muted text-sm mt-1">
          This helps Surge improve its predictions.
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
        Share your actual stats to help improve Surge&apos;s predictions.
      </p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
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
      </form>
      {error && <p className="text-danger text-sm mt-2">{error}</p>}
    </div>
  );
}
