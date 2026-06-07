import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background:     "var(--color-background)",
        surface:        "var(--color-surface)",
        card:           "var(--color-card)",
        border:         "var(--color-border)",
        "purple-from":  "var(--color-purple-from)",
        "purple-to":    "var(--color-purple-to)",
        "blue-from":    "var(--color-blue-from)",
        "blue-to":      "var(--color-blue-to)",
        "text-primary": "var(--color-text-primary)",
        "text-muted":   "var(--color-text-muted)",
        success:        "var(--color-success)",
        warning:        "var(--color-warning)",
        danger:         "var(--color-danger)",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
