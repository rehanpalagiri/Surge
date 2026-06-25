"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ReportSkeleton } from "@/components/Skeleton";

/**
 * Single source of truth for the "analyzing your video" experience.
 *
 * Two phases, driven by one honest percentage:
 *   1. Meter      — a clean progress bar with a real % number underneath, while
 *                   the review is being built. This is what the user sees for
 *                   most of the wait.
 *   2. Near-done  — once the percentage crosses `revealAt` (≈ the home stretch,
 *                   "almost done / a few seconds left"), the report skeleton
 *                   fades in beneath a slim top bar so the results feel like
 *                   they're materializing. The skeleton is NOT shown the whole
 *                   time — only at the end, which is the whole point.
 *
 * The percentage is time-based (eases toward ~90% over `expectedMs`, then
 * crawls) so it tracks elapsed work instead of jumping. When the caller signals
 * `done`, it snaps to 100. We never claim 100% before the work is actually done.
 */

const TICK_MS = 120; // ~8 fps state updates; the bar's CSS transition smooths it

function useSmoothProgress(active: boolean, done: boolean, expectedMs: number): number {
  const [pct, setPct] = useState(0);
  const startRef = useRef(0);

  useEffect(() => {
    if (!active) {
      setPct(0);
      return;
    }
    startRef.current = performance.now();
    const id = setInterval(() => {
      const elapsed = performance.now() - startRef.current;
      // Ease-out 0 → 90 over expectedMs, then a slow crawl 90 → 97 so it never
      // looks stalled and never looks finished early.
      const t = Math.min(1, elapsed / expectedMs);
      const eased = 90 * (1 - Math.pow(1 - t, 2.2));
      const crawl = elapsed > expectedMs ? Math.min(7, ((elapsed - expectedMs) / 5000) * 7) : 0;
      const target = Math.min(97, eased + crawl);
      setPct((prev) => (target > prev ? target : prev)); // monotonic — never goes backwards
    }, TICK_MS);
    return () => clearInterval(id);
  }, [active, expectedMs]);

  // Real completion wins immediately.
  useEffect(() => {
    if (done) setPct(100);
  }, [done]);

  return pct;
}

function useRotatingStep(steps: string[], active: boolean, intervalMs = 3500): string {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!active || steps.length <= 1) return;
    setI(0);
    const id = setInterval(() => setI((n) => Math.min(n + 1, steps.length - 1)), intervalMs);
    return () => clearInterval(id);
  }, [active, steps.length, intervalMs]);
  return steps[Math.min(i, steps.length - 1)] ?? "";
}

export interface AnalysisProgressProps {
  active: boolean;
  /** Set true the instant the real work finishes — snaps the bar to 100%. */
  done?: boolean;
  title?: string;
  steps?: string[];
  /** Expected wall-clock duration used to pace the bar (ms). */
  expectedMs?: number;
  /** Percentage at which the skeleton is revealed ("almost done"). */
  revealAt?: number;
  compact?: boolean;
}

const DEFAULT_STEPS = [
  "Analyzing the first-3-second hook…",
  "Scanning for on-screen text collisions…",
  "Measuring cut rhythm and pacing…",
  "Checking audio-visual sync and loop…",
  "Writing your craft review…",
];

/**
 * The inner experience (no overlay chrome) — drop it straight into a page, or
 * wrap it with <AnalysisOverlay> for the full-screen upload flow.
 */
export function AnalysisProgress({
  active,
  done = false,
  title = "Analyzing your video",
  steps = DEFAULT_STEPS,
  expectedMs = 26000,
  revealAt = 88,
  compact = false,
}: AnalysisProgressProps) {
  const pct = useSmoothProgress(active, done, expectedMs);
  const step = useRotatingStep(steps, active);
  const rounded = Math.round(pct);
  const revealed = pct >= revealAt;

  // The skeleton tree is static; memoize it so the ~8fps progress ticks only
  // re-paint the bar + percentage, not the whole placeholder report.
  const skeleton = useMemo(() => <ReportSkeleton compact={compact} />, [compact]);

  if (revealed) {
    // ── Near-done: slim top bar + the skeleton "materializing" ──
    return (
      <div className="w-full" role="status" aria-live="polite">
        <div className="mb-5 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-semibold text-white">Building your review…</span>
            <span className="tabular-nums font-semibold text-purple-300">{rounded}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-purple-600 to-purple-400"
              style={{ width: `${pct}%`, transition: "width 400ms cubic-bezier(0.25, 1, 0.5, 1)" }}
            />
          </div>
          <p className="text-center text-xs text-zinc-500 animate-pulse">{step}</p>
        </div>
        {skeleton}
      </div>
    );
  }

  // ── Meter: the main wait, a clean bar with the % right under it ──
  return (
    <div className="flex w-full flex-col items-center gap-6 py-6" role="status" aria-live="polite">
      <div className="text-center space-y-1.5">
        <p className="text-xl font-bold text-white">{title}…</p>
        <p className="text-sm text-zinc-500">Hang tight — your craft review is being written</p>
      </div>

      <div className="w-full max-w-sm space-y-2.5">
        <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-purple-600 to-purple-400"
            style={{ width: `${pct}%`, transition: "width 400ms cubic-bezier(0.25, 1, 0.5, 1)" }}
          />
        </div>
        {/* the percentage, right under the bar */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-zinc-500 animate-pulse">{step}</span>
          <span className="text-sm font-bold tabular-nums text-purple-300">{rounded}%</span>
        </div>
      </div>
    </div>
  );
}

/** Full-screen overlay wrapper for the upload/analyze flow. */
export function AnalysisOverlay(props: AnalysisProgressProps & { label?: string }) {
  const { label = "Preparing your craft review", ...rest } = props;
  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-zinc-950/98 backdrop-blur-sm px-4 py-10"
      role="dialog"
      aria-modal="true"
      aria-busy="true"
      aria-label={label}
    >
      <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col items-center justify-center">
        <AnalysisProgress {...rest} />
      </div>
    </div>
  );
}
