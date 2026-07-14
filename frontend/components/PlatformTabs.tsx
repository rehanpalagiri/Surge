"use client";

export type Platform = "tiktok" | "instagram";

const TABS: { id: Platform; label: string }[] = [
  { id: "tiktok", label: "TikTok" },
  { id: "instagram", label: "Instagram" },
];

/**
 * Sliding platform switcher. A single pill snaps between TikTok and Instagram,
 * and the pill uses the shared magnetic-pink action color for either platform.
 * Reused on every page that toggles platform so the interaction is identical
 * everywhere.
 */
export default function PlatformTabs({
  value,
  onChange,
  className = "",
}: {
  value: Platform;
  onChange: (p: Platform) => void;
  className?: string;
}) {
  const activeIndex = Math.max(0, TABS.findIndex((t) => t.id === value));

  return (
    <div
      role="tablist"
      aria-label="Platform"
      className={`relative grid grid-cols-2 rounded-2xl border border-border bg-card p-1 ${className}`}
    >
      {/* Sliding indicator — snaps between the two equal-width cells and
          carries the active platform's brand fill. */}
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute top-1 bottom-1 left-1 rounded-xl shadow-md transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
          "brand-tab-pink"
        }`}
        style={{
          width: "calc((100% - 0.5rem) / 2)",
          transform: `translateX(${activeIndex * 100}%)`,
        }}
      />
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={`relative z-10 rounded-xl px-6 py-2.5 text-sm font-semibold transition-colors ${
            value === t.id
              ? "text-black"
              : "text-text-muted hover:text-text-primary"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
