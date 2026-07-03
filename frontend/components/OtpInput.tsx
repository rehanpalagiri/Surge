"use client";

import { useRef } from "react";

/**
 * Six-box 6-digit code input. Slots render empty (not a space) so typing is
 * never blocked, supports paste, backspace, and arrow navigation. Shared by the
 * password-reset and email-verification flows.
 */
export default function OtpInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const r0 = useRef<HTMLInputElement>(null);
  const r1 = useRef<HTMLInputElement>(null);
  const r2 = useRef<HTMLInputElement>(null);
  const r3 = useRef<HTMLInputElement>(null);
  const r4 = useRef<HTMLInputElement>(null);
  const r5 = useRef<HTMLInputElement>(null);
  const refs = [r0, r1, r2, r3, r4, r5];
  // padEnd with " " (space) so we always get 6 slots; .replace(/ /g,"") strips
  // them back out when building the next state string. padEnd(6,"") is a no-op
  // per JS spec (empty padString can't lengthen the string), which would cause
  // digits=[] and make typed characters silently disappear.
  const digits = value.padEnd(6, " ").split("").slice(0, 6);

  function focus(i: number) {
    refs[i]?.current?.focus();
  }

  function handleChange(i: number, raw: string) {
    const digit = raw.replace(/\D/g, "").slice(-1);
    const next = digits.map((d, idx) => (idx === i ? digit : d)).join("").replace(/ /g, "");
    onChange(next);
    if (digit && i < 5) setTimeout(() => focus(i + 1), 0);
  }

  function handleKeyDown(i: number, e: React.KeyboardEvent) {
    if (e.key === "Backspace") {
      if (digits[i].trim()) {
        const next = digits.map((d, idx) => (idx === i ? "" : d)).join("").replace(/ /g, "");
        onChange(next);
      } else if (i > 0) {
        focus(i - 1);
      }
    } else if (e.key === "ArrowLeft" && i > 0) {
      focus(i - 1);
    } else if (e.key === "ArrowRight" && i < 5) {
      focus(i + 1);
    }
  }

  function handlePaste(e: React.ClipboardEvent) {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    onChange(pasted);
    const nextIdx = Math.min(pasted.length, 5);
    setTimeout(() => focus(nextIdx), 0);
  }

  return (
    <div className="flex items-end justify-center gap-2">
      {[0, 1, 2].map((i) => (
        <input
          key={i}
          ref={refs[i]}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={digits[i].trim()}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          className="w-10 h-14 bg-transparent border-b-2 border-text-primary text-text-primary text-3xl font-bold text-center focus:outline-none focus:border-accent caret-transparent"
        />
      ))}
      <span className="text-text-muted text-2xl pb-2 px-1 select-none">·</span>
      {[3, 4, 5].map((i) => (
        <input
          key={i}
          ref={refs[i]}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={digits[i].trim()}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          className="w-10 h-14 bg-transparent border-b-2 border-text-primary text-text-primary text-3xl font-bold text-center focus:outline-none focus:border-accent caret-transparent"
        />
      ))}
    </div>
  );
}
