import { useState, useEffect } from "react";

/**
 * Indeterminate progress bar value (0–100) for long async work with no real
 * percentage. While `active`, it snaps to `snapTo` then eases toward ~88% and
 * holds (so it never looks finished before the work is). Resets to 0 when idle.
 * Shared by the upload and analysis overlays so the easing stays in one place.
 */
export function useFakeProgress(active: boolean, snapTo = 20): number {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!active) {
      setProgress(0);
      return;
    }
    setProgress(0);
    const snap = setTimeout(() => setProgress(snapTo), 80);
    const crawl = setInterval(() => {
      setProgress((p) => (p >= 88 ? p : p + Math.max(0.3, (88 - p) * 0.018)));
    }, 500);
    return () => {
      clearTimeout(snap);
      clearInterval(crawl);
    };
  }, [active, snapTo]);

  return progress;
}
