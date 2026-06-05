"use client";

import { useEffect, useState } from "react";

interface ScoreBarProps {
  label: string;
  score: number;   // 0–10
  animate?: boolean;
  delay?: number;
}

export default function ScoreBar({
  label,
  score,
  animate = true,
  delay = 0,
}: ScoreBarProps) {
  const [displayed, setDisplayed] = useState(0);

  useEffect(() => {
    if (!animate) {
      setDisplayed(score);
      return;
    }
    const timer = setTimeout(() => {
      setDisplayed(score);
    }, delay);
    return () => clearTimeout(timer);
  }, [score, animate, delay]);

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
