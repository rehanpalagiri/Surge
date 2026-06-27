"use client";

import { useEffect } from "react";
import Link from "next/link";
import { track } from "@vercel/analytics";

interface UpsellModalProps {
  analysisId: number | string;
  onClose: () => void;
}

export default function UpsellModal({ analysisId, onClose }: UpsellModalProps) {
  useEffect(() => {
    track("upsell_shown", { analysis_id: analysisId });
  }, [analysisId]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4 bg-black/70 backdrop-blur-sm motion-enter"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="relative w-full max-w-md rounded-2xl p-[1.5px] gradient-btn motion-pop"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rounded-2xl bg-card p-7 text-center">
          {/* Close */}
          <button
            onClick={onClose}
            aria-label="Close"
            className="absolute top-3 right-4 text-text-muted hover:text-text-primary text-2xl leading-none"
          >
            ×
          </button>

          <h2 className="text-2xl font-extrabold text-text-primary mb-3">
            Your craft review is just the start
          </h2>
          <p className="text-text-muted leading-relaxed mb-6">
            Sign up free to unlock timestamped attention observations, editing hypotheses,
            hook and caption alternatives, and one clearly defined experiment to test next.
          </p>

          <div className="flex flex-col gap-3">
            <Link
              href={`/signup?next=/results/${analysisId}`}
              onClick={() => track("upsell_cta_clicked", { analysis_id: analysisId })}
              className="gradient-btn text-white font-bold py-3 rounded-xl hover:scale-[1.02] active:scale-[0.98] transition-transform"
            >
              Get my full craft review
            </Link>
            <button
              onClick={onClose}
              className="text-text-muted hover:text-text-primary text-sm py-1"
            >
              Maybe later
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
