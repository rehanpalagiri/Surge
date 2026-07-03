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
        "text-primary": "var(--color-text-primary)",
        "text-muted":   "var(--color-text-muted)",
        accent:         "var(--color-accent)",
        success:        "var(--color-success)",
        warning:        "var(--color-warning)",
        danger:         "var(--color-danger)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "Georgia", "serif"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
