"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ReportSkeleton } from "@/components/Skeleton";

/**
 * Single source of truth for the "analyzing your video" experience.
 *
 * Two phases:
 *   1. Meter    — progress bar with live percentage + ETA, covering most of the wait.
 *   2. Near-done — once the bar crosses `revealAt` the skeleton fades in beneath a
 *                  slim top bar so results feel like they're materializing.
 *
 * The bar is time-based (eases to ~90% over `expectedMs`, crawls to 99 after that).
 * When `done` is set: the bar jumps to `revealAt` (showing the skeleton immediately),
 * holds for `skelHoldMs`, snaps to 100, then calls `onComplete` — giving users a
 * guaranteed 3-4 second skeleton view before results appear.
 */

const TICK_MS = 120;

function useSmoothProgress(
  active: boolean,
  expectedMs: number,
): [number, React.Dispatch<React.SetStateAction<number>>, number] {
  const [pct, setPct] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(0);

  useEffect(() => {
    if (!active) {
      setPct(0);
      setElapsed(0);
      return;
    }
    startRef.current = performance.now();
    const id = setInterval(() => {
      const ms = performance.now() - startRef.current;
      setElapsed(ms);
      const t = Math.min(1, ms / expectedMs);
      const eased = 90 * (1 - Math.pow(1 - t, 2.2));
      const crawl = ms > expectedMs ? Math.min(9, ((ms - expectedMs) / 5000) * 9) : 0;
      const target = Math.min(99, eased + crawl);
      setPct((prev) => (target > prev ? target : prev));
    }, TICK_MS);
    return () => clearInterval(id);
  }, [active, expectedMs]);

  return [pct, setPct, elapsed];
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

function etaText(elapsed: number, expectedMs: number, pct: number): string {
  if (pct >= 90) return "Almost there…";
  const remainingMs = Math.max(0, expectedMs - elapsed);
  const secs = Math.ceil(remainingMs / 1000);
  if (secs <= 5) return "A few seconds left…";
  if (secs < 60) return `~${secs}s left`;
  return `~${Math.ceil(secs / 60)}m left`;
}

export interface AnalysisProgressProps {
  active: boolean;
  /** Set true the instant the real work finishes — triggers the skeleton hold then onComplete. */
  done?: boolean;
  /** Called after the skeleton has been visible for `skelHoldMs` ms. Use this to unmount
   *  this component and reveal actual results — do NOT unmount before onComplete fires. */
  onComplete?: () => void;
  /** How long (ms) to hold the skeleton after `done` before calling onComplete. Default 3 500. */
  skelHoldMs?: number;
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
  "Checking audio-visual sync and the ending…",
  "Writing your craft review…",
];

export function AnalysisProgress({
  active,
  done = false,
  onComplete,
  skelHoldMs = 3500,
  title = "Analyzing your video",
  steps = DEFAULT_STEPS,
  expectedMs = 8000,
  revealAt = 99,
  compact = false,
}: AnalysisProgressProps) {
  const [pct, setPct, elapsed] = useSmoothProgress(active, expectedMs);
  const step = useRotatingStep(steps, active);
  const rounded = Math.round(pct);
  const revealed = pct >= revealAt;

  // When done fires: jump to revealAt (shows skeleton), hold skelHoldMs, then complete.
  useEffect(() => {
    if (!done) return;
    setPct((prev) => Math.max(prev, revealAt));
    const timer = setTimeout(() => {
      setPct(100);
      onComplete?.();
    }, skelHoldMs);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done]);

  const skeleton = useMemo(() => <ReportSkeleton compact={compact} />, [compact]);

  if (revealed) {
    return (
      <div className="w-full" role="status" aria-live="polite">
        <div className="mb-5 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-semibold text-text-primary">Building your review…</span>
            <span className="tabular-nums font-semibold text-accent">{rounded}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full bg-accent"
              style={{ width: `${pct}%`, transition: "width 400ms cubic-bezier(0.25, 1, 0.5, 1)" }}
            />
          </div>
          <p className="text-center text-xs text-text-muted animate-pulse">{step}</p>
        </div>
        {skeleton}
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col items-center gap-6 py-6" role="status" aria-live="polite">
      <div className="text-center space-y-1.5">
        <p className="text-xl font-bold text-text-primary">{title}…</p>
        <p className="text-sm text-text-muted">Hang tight — your craft review is being written</p>
      </div>

      <div className="w-full max-w-sm space-y-2.5">
        <div className="h-2 w-full overflow-hidden rounded-full bg-border">
          <div
            className="h-full rounded-full bg-accent"
            style={{ width: `${pct}%`, transition: "width 400ms cubic-bezier(0.25, 1, 0.5, 1)" }}
          />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-text-muted animate-pulse">{step}</span>
          <span className="text-sm font-bold tabular-nums text-accent">{rounded}%</span>
        </div>
        {/* Live ETA — shown while bar is in the main meter phase */}
        <p className="text-center text-xs text-text-muted/80">
          {etaText(elapsed, expectedMs, pct)}
        </p>
      </div>
    </div>
  );
}

/** Full-screen overlay wrapper for the upload/analyze flow. */
export function AnalysisOverlay(props: AnalysisProgressProps & { label?: string }) {
  const { label = "Preparing your craft review", ...rest } = props;
  return (
    <div
      className="analysis-page fixed inset-0 z-50 overflow-y-auto bg-white px-4 py-10"
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
