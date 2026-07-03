"use client";

import { useEffect, useState } from "react";

const DISMISSED_KEY = "surge-install-dismissed";

export default function InstallBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    if (!isMobile) return;

    // Don't show when already running as installed PWA
    const isStandalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true;
    if (isStandalone) return;

    if (localStorage.getItem(DISMISSED_KEY)) return;

    const t = setTimeout(() => setShow(true), 2000);
    return () => clearTimeout(t);
  }, []);

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, "1");
    setShow(false);
  }

  if (!show) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 z-50 bg-card border border-accent/40 rounded-2xl p-4 shadow-2xl flex items-start gap-3 motion-pop">
      <div className="flex-1 min-w-0">
        <p className="text-text-primary text-sm font-semibold">
          Add Surge to your Home Screen
        </p>
        <p className="text-text-muted text-xs mt-0.5 leading-relaxed">
          Tap <span className="text-accent font-medium">Share</span> →{" "}
          <span className="text-accent font-medium">Add to Home Screen</span> for
          the best experience.
        </p>
      </div>
      <button
        onClick={dismiss}
        aria-label="Dismiss"
        className="text-text-muted hover:text-text-primary text-xl leading-none flex-shrink-0 -mt-0.5 px-1"
      >
        ✕
      </button>
    </div>
  );
}
