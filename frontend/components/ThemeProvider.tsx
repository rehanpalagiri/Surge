"use client";

import { useEffect } from "react";

export const THEME_KEY = "surge_theme";

/** Applies the saved theme class to <html> on mount and whenever storage changes. */
export default function ThemeProvider() {
  useEffect(() => {
    const apply = () => {
      const saved = localStorage.getItem(THEME_KEY);
      if (saved === "light") {
        document.documentElement.classList.add("light");
      } else {
        document.documentElement.classList.remove("light");
      }
    };
    apply();
    window.addEventListener("storage", apply);
    window.addEventListener("surge-theme", apply);
    return () => {
      window.removeEventListener("storage", apply);
      window.removeEventListener("surge-theme", apply);
    };
  }, []);

  return null;
}
