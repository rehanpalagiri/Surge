"use client";

import { useEffect, useState } from "react";

interface ScoreBarProps {
  label: string;
  /** 0–10, or null when the review marked this dimension not applicable. */
  score: number | null;
  /** Why the dimension wasn't scored (deliberate format choice). */
  naReason?: string;
  animate?: boolean;
  delay?: number;
}

export default function ScoreBar({
  label,
  score,
  naReason,
  animate = true,
  delay = 0,
}: ScoreBarProps) {
  const [displayed, setDisplayed] = useState(0);
  const numeric = score ?? 0;

  useEffect(() => {
    if (score == null) return;
    if (!animate) {
      setDisplayed(numeric);
      return;
    }
    const timer = setTimeout(() => {
      setDisplayed(numeric);
    }, delay);
    return () => clearTimeout(timer);
  }, [score, numeric, animate, delay]);

  // Not scored — a deliberate format choice, not a failure. Render it calm.
  if (score == null) {
    return (
      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between items-center">
          <span className="text-sm text-text-muted font-medium">{label}</span>
          <span className="text-sm font-semibold text-text-muted">n/a</span>
        </div>
        <div className="h-2.5 rounded-full border border-dashed border-border" />
        <p className="text-xs text-text-muted/80">
          Not scored{naReason ? ` — ${naReason}` : " — not applicable to this format"}
        </p>
      </div>
    );
  }

  const color =
    score >= 7
      ? "bg-success"
      : score >= 4
      ? "bg-warning"
      : "bg-danger";

  const textColor =
    score >= 7
      ? "text-success"
      : score >= 4
      ? "text-warning"
      : "text-danger";

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between items-center">
        <span className="text-sm text-text-muted font-medium">{label}</span>
        <span className={`text-sm font-bold ${textColor}`}>{score}/10</span>
      </div>
      <div className="h-2.5 bg-surface rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${color}`}
          style={{ width: `${(displayed / 10) * 100}%` }}
        />
      </div>
    </div>
  );
}
