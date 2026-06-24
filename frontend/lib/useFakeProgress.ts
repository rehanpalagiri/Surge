import { useState, useEffect } from "react";

/**
 * Indeterminate progress value (0–100) for long async work with no real
 * percentage. While `active`, it rushes quickly to ~90% (so it feels
 * responsive), then crawls slowly toward ~98% and holds — it never reaches
 * 100% before the work actually finishes. Resets to 0 when idle.
 * Shared by the upload and analysis overlays so the easing stays in one place.
 * `snapTo` optionally sets the starting value when work begins.
 */
export function useFakeProgress(active: boolean, snapTo = 0): number {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!active) {
      setProgress(0);
      return;
    }
    setProgress(snapTo);
    const tick = setInterval(() => {
      setProgress((p) => {
        // Fast ease-out to ~90%, then a slow crawl so it never looks finished.
        if (p < 90) return p + (90 - p) * 0.16;
        if (p < 98) return p + (98 - p) * 0.012;
        return p;
      });
    }, 80);
    return () => clearInterval(tick);
  }, [active, snapTo]);

  return progress;
}
