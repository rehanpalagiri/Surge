"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronDown, X, Check, Search } from "lucide-react";

// Mirrors backend CANONICAL_NICHES (services/niche_classifier.py). Sending these exact
// labels lets the backend exact-match them (no extra Gemini classify call). Search +
// custom entry mean the chip list never has to be exhaustive.
export const NICHE_OPTIONS = [
  "Fitness", "Comedy", "Food", "Fashion", "Beauty",
  "Education", "Gaming", "Music", "Dance", "Tech",
  "Finance", "Money", "Side Hustles", "Crypto", "Business",
  "Health", "Mental Health", "Yoga", "Travel", "Lifestyle",
  "Motivation", "Sports", "Dating", "Art", "Pets",
  "Parenting", "Kids", "Vegan", "DIY & Crafts", "Home Decor",
  "Cleaning", "Career", "Real Estate", "Outdoors", "True Crime",
  "Books", "Spirituality", "Movies & TV", "Anime", "Edits",
  "Cars", "Photography", "Video Production", "Sustainability", "College", "Luxury",
  "Thrifting", "Hair", "Looksmaxxing", "ASMR", "News",
];

interface Props {
  selected: string[];
  onChange: (next: string[]) => void;
  max?: number;
}

export default function NichePicker({ selected, onChange, max = 2 }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const ref = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Close on outside click.
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  // Reset highlight when query changes or dropdown opens.
  useEffect(() => { setHighlightedIndex(-1); }, [query, open]);

  // Scroll highlighted item into view.
  useEffect(() => {
    if (highlightedIndex < 0 || !listRef.current) return;
    const el = listRef.current.querySelector<HTMLElement>(`[data-idx="${highlightedIndex}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [highlightedIndex]);

  const atMax = selected.length >= max;
  const q = query.trim().toLowerCase();
  const filtered = NICHE_OPTIONS.filter((n) => n.toLowerCase().includes(q));
  const exactExists =
    NICHE_OPTIONS.some((n) => n.toLowerCase() === q) ||
    selected.some((n) => n.toLowerCase() === q);
  const showCustom = !!q && !exactExists && !atMax;

  // Navigable items: filtered list + custom entry slot.
  const navItems: string[] = [...filtered, ...(showCustom ? ["__custom__"] : [])];

  const select = (n: string) => {
    if (!selected.includes(n) && !atMax) {
      onChange([...selected, n]);
      setQuery("");
      setOpen(false);
    }
  };

  const deselect = (n: string) => onChange(selected.filter((x) => x !== n));

  const toggle = (n: string) => {
    if (selected.includes(n)) deselect(n);
    else select(n);
  };

  const addCustom = () => {
    const v = query.trim();
    if (v && !atMax && !selected.some((s) => s.toLowerCase() === v.toLowerCase())) {
      onChange([...selected, v]);
      setQuery("");
      setOpen(false);
    }
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, navItems.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, -1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlightedIndex >= 0 && highlightedIndex < navItems.length) {
        const item = navItems[highlightedIndex];
        if (item === "__custom__") addCustom();
        else toggle(item);
      } else if (showCustom) {
        addCustom();
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  // Reorder which niche is primary. Order is meaningful: selected[0] is the spine that
  // sets the review context; selected[1] only nudges the weighting.
  const swap = () => {
    if (selected.length === 2) onChange([selected[1], selected[0]]);
  };

  return (
    <div className="space-y-2" ref={ref}>
      <div className="flex items-baseline justify-between">
        <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">Niche Hint</p>
        <p className="text-[11px] text-text-muted">primary + optional 2nd</p>
      </div>

      {/* Field */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen((o) => !o); } }}
        className="w-full flex items-center gap-2 min-h-[48px] bg-surface border border-border rounded-xl px-3 py-2 cursor-pointer hover:border-accent/50 focus:outline-none focus:border-accent transition-colors"
      >
        <div className="flex flex-wrap gap-1.5 flex-1 min-w-0">
          {selected.length === 0 ? (
            <span className="text-text-muted text-sm">Optional: choose up to 2 niches…</span>
          ) : (
            selected.map((n, i) => (
              <span
                key={n}
                className={`inline-flex items-center gap-1.5 text-xs font-medium pl-1.5 pr-1 py-1 rounded-full ${
                  i === 0
                    ? "bg-accent/30 border border-accent/60 text-text-primary"
                    : "bg-card border border-border text-text-primary"
                }`}
              >
                <span
                  className={`flex items-center justify-center px-1.5 h-4 rounded-full text-[9px] font-bold uppercase tracking-wide ${
                    i === 0 ? "bg-accent text-background" : "bg-border text-text-primary"
                  }`}
                >
                  {i === 0 ? "Primary" : "2nd"}
                </span>
                {n}
                <button
                  type="button"
                  aria-label={`Remove ${n}`}
                  onClick={(e) => { e.stopPropagation(); deselect(n); }}
                  className="hover:bg-white/10 rounded-full p-0.5 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))
          )}
        </div>
        <ChevronDown className={`w-4 h-4 text-text-muted shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </div>

      {/* Dropdown */}
      {open && (
        <div className="relative">
          <div className="absolute z-30 mt-1 w-full bg-card border border-border rounded-xl shadow-2xl shadow-black/50 overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
              <Search className="w-4 h-4 text-text-muted shrink-0" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleInputKeyDown}
                placeholder="Search niches or type your own…"
                className="flex-1 bg-transparent text-text-primary text-sm placeholder:text-text-muted focus:outline-none"
              />
            </div>
            <div ref={listRef} className="max-h-60 overflow-y-auto py-1">
              {filtered.length === 0 && q && (
                <p className="px-3 pt-3 pb-1 text-sm text-text-muted text-center">
                  No results for &ldquo;<span className="text-text-primary">{query.trim()}</span>&rdquo;
                </p>
              )}
              {filtered.map((n, idx) => {
                const sel = selected.includes(n);
                const disabled = atMax && !sel;
                const highlighted = highlightedIndex === idx;
                return (
                  <button
                    key={n}
                    type="button"
                    data-idx={idx}
                    disabled={disabled}
                    onClick={() => toggle(n)}
                    className={`w-full flex items-center justify-between px-3 py-2 text-sm text-left transition-colors ${
                      sel
                        ? "text-accent bg-accent/10"
                        : disabled
                        ? "text-text-muted/50 cursor-not-allowed"
                        : highlighted
                        ? "text-text-primary bg-surface"
                        : "text-text-primary hover:bg-surface"
                    }`}
                  >
                    {n}
                    {sel && <Check className="w-4 h-4 text-accent shrink-0" />}
                  </button>
                );
              })}
              {showCustom && (
                <button
                  type="button"
                  data-idx={filtered.length}
                  disabled={atMax}
                  onClick={addCustom}
                  className={`w-full px-3 py-2 text-sm text-left transition-colors ${
                    atMax
                      ? "text-text-muted/50 cursor-not-allowed"
                      : highlightedIndex === filtered.length
                      ? "text-text-primary bg-surface"
                      : "text-text-primary hover:bg-surface"
                  }`}
                >
                  Use &ldquo;<span className="text-accent font-medium">{query.trim()}</span>&rdquo;
                </button>
              )}
              {filtered.length === 0 && !q && (
                <p className="px-3 py-3 text-sm text-text-muted text-center">No niches</p>
              )}
            </div>
            {atMax && (
              <div className="px-3 py-2 text-[11px] text-text-muted border-t border-border">
                2 niches max — remove one to pick a different one.
              </div>
            )}
          </div>
        </div>
      )}

      {selected.length === 1 && (
        <p className="text-[11px] text-text-muted">
          <span className="text-accent font-medium">{selected[0]}</span> is the{" "}
          <span className="text-text-muted">primary</span> hint. Add a 2nd for a blend.
        </p>
      )}

      {selected.length === 2 && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] text-text-muted">
            <span className="text-accent font-medium">{selected[0]}</span> leads the review ·{" "}
            <span className="text-text-muted font-medium">{selected[1]}</span> adds nuance
          </p>
          <button
            type="button"
            onClick={swap}
            className="shrink-0 text-[11px] font-medium text-text-muted hover:text-accent transition-colors"
          >
            ⇄ Swap primary
          </button>
        </div>
      )}
    </div>
  );
}
