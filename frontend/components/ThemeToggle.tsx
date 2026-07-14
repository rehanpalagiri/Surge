"use client";

import { useEffect, useLayoutEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

type Theme = "dark" | "light";

// Read the real theme (set pre-paint by the inline script in layout.tsx) in a
// layout effect so the icon is corrected before the browser paints — a plain
// effect runs after paint, flashing the Sun for one frame to light-theme users.
// Fall back to useEffect on the server to avoid React's SSR useLayoutEffect warning.
const useIsomorphicLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

/**
 * Light/dark switch for the Noir theme. The real source of truth is the
 * data-theme attribute on <html>, set before paint by the inline script in
 * app/layout.tsx; this button just flips it and persists the choice. The first
 * render matches the SSR markup (a disabled Sun); the layout effect then syncs
 * the icon to the actual theme before paint, so there's no visible flicker.
 */
export default function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useState<Theme | null>(null);

  useIsomorphicLayoutEffect(() => {
    setTheme(
      document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark"
    );
  }, []);

  const toggle = () => {
    const next: Theme = theme === "light" ? "dark" : "light";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("surge-theme", next);
    } catch {
      // Private-mode storage failures just lose persistence, not the switch.
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={theme === null}
      aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
      title={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
      className={`theme-toggle ${className}`}
    >
      {theme === "light" ? <Moon size={15} /> : <Sun size={15} />}
    </button>
  );
}
