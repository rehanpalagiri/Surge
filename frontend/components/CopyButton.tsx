"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

/** Small copy-to-clipboard affordance for generated text (hooks, captions). */
export default function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard unavailable (permissions/insecure context) — leave the
      // text selectable; the button just won't confirm.
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-live="polite"
      className="inline-flex items-center gap-1.5 text-xs font-semibold text-text-muted hover:text-text-primary border border-border hover:border-accent/50 rounded-lg px-2.5 py-1.5 transition-colors"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-success" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
      {copied ? "Copied" : label}
    </button>
  );
}
