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
  "Cars", "Photography", "Sustainability", "College", "Luxury",
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
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click.
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const atMax = selected.length >= max;
  const q = query.trim().toLowerCase();
  const filtered = NICHE_OPTIONS.filter((n) => n.toLowerCase().includes(q));
  const exactExists =
    NICHE_OPTIONS.some((n) => n.toLowerCase() === q) ||
    selected.some((n) => n.toLowerCase() === q);

  const toggle = (n: string) => {
    if (selected.includes(n)) onChange(selected.filter((x) => x !== n));
    else if (!atMax) onChange([...selected, n]);
  };

  const addCustom = () => {
    const v = query.trim();
    if (v && !atMax && !selected.some((s) => s.toLowerCase() === v.toLowerCase())) {
      onChange([...selected, v]);
      setQuery("");
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
        <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Content Niche</p>
        <p className="text-[11px] text-zinc-500">primary + optional 2nd</p>
      </div>

      {/* Field */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen((o) => !o); } }}
        className="w-full flex items-center gap-2 min-h-[48px] bg-zinc-900 border border-zinc-700 rounded-xl px-3 py-2 cursor-pointer hover:border-zinc-600 focus:outline-none focus:border-purple-500 transition-colors"
      >
        <div className="flex flex-wrap gap-1.5 flex-1 min-w-0">
          {selected.length === 0 ? (
            <span className="text-zinc-500 text-sm">Select up to 2 niches…</span>
          ) : (
            selected.map((n, i) => (
              <span
                key={n}
                className={`inline-flex items-center gap-1.5 text-xs font-medium pl-1.5 pr-1 py-1 rounded-full ${
                  i === 0
                    ? "bg-purple-600/30 border border-purple-500/60 text-purple-50"
                    : "bg-zinc-800 border border-zinc-600 text-zinc-300"
                }`}
              >
                <span
                  className={`flex items-center justify-center px-1.5 h-4 rounded-full text-[9px] font-bold uppercase tracking-wide ${
                    i === 0 ? "bg-purple-500 text-white" : "bg-zinc-600 text-zinc-200"
                  }`}
                >
                  {i === 0 ? "Primary" : "2nd"}
                </span>
                {n}
                <button
                  type="button"
                  aria-label={`Remove ${n}`}
                  onClick={(e) => { e.stopPropagation(); toggle(n); }}
                  className="hover:bg-white/10 rounded-full p-0.5 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))
          )}
        </div>
        <ChevronDown className={`w-4 h-4 text-zinc-500 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </div>

      {/* Dropdown */}
      {open && (
        <div className="relative">
          <div className="absolute z-30 mt-1 w-full bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl shadow-black/50 overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2.5 border-b border-zinc-800">
              <Search className="w-4 h-4 text-zinc-500 shrink-0" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (!exactExists && q) addCustom(); } }}
                placeholder="Search niches or type your own…"
                className="flex-1 bg-transparent text-white text-sm placeholder:text-zinc-500 focus:outline-none"
              />
            </div>
            <div className="max-h-60 overflow-y-auto py-1">
              {filtered.map((n) => {
                const sel = selected.includes(n);
                const disabled = atMax && !sel;
                return (
                  <button
                    key={n}
                    type="button"
                    disabled={disabled}
                    onClick={() => toggle(n)}
                    className={`w-full flex items-center justify-between px-3 py-2 text-sm text-left transition-colors ${
                      sel
                        ? "text-purple-200 bg-purple-600/10"
                        : disabled
                        ? "text-zinc-600 cursor-not-allowed"
                        : "text-zinc-200 hover:bg-zinc-800"
                    }`}
                  >
                    {n}
                    {sel && <Check className="w-4 h-4 text-purple-400 shrink-0" />}
                  </button>
                );
              })}
              {q && !exactExists && (
                <button
                  type="button"
                  disabled={atMax}
                  onClick={addCustom}
                  className={`w-full px-3 py-2 text-sm text-left ${atMax ? "text-zinc-600 cursor-not-allowed" : "text-zinc-200 hover:bg-zinc-800"}`}
                >
                  Use &ldquo;<span className="text-purple-300 font-medium">{query.trim()}</span>&rdquo;
                </button>
              )}
              {filtered.length === 0 && !q && (
                <p className="px-3 py-3 text-sm text-zinc-500 text-center">No niches</p>
              )}
            </div>
            {atMax && (
              <div className="px-3 py-2 text-[11px] text-zinc-500 border-t border-zinc-800">
                2 niches max — remove one to pick a different one.
              </div>
            )}
          </div>
        </div>
      )}

      {selected.length === 1 && (
        <p className="text-[11px] text-zinc-500">
          <span className="text-purple-300 font-medium">{selected[0]}</span> is your{" "}
          <span className="text-zinc-400">primary</span> niche — it sets the craft context. Add a 2nd for a blend.
        </p>
      )}

      {selected.length === 2 && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] text-zinc-500">
            <span className="text-purple-300 font-medium">{selected[0]}</span> leads the review ·{" "}
            <span className="text-zinc-400 font-medium">{selected[1]}</span> adds nuance
          </p>
          <button
            type="button"
            onClick={swap}
            className="shrink-0 text-[11px] font-medium text-zinc-400 hover:text-purple-300 transition-colors"
          >
            ⇄ Swap primary
          </button>
        </div>
      )}
    </div>
  );
}
