"use client";

import { useState } from "react";

export default function ReportIssue() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");

  function submit() {
    const subject = encodeURIComponent("Surge Bug Report");
    const body = encodeURIComponent(text.trim() || "(no description provided)");
    window.open(`mailto:irehan29@icloud.com?subject=${subject}&body=${body}`);
    setOpen(false);
    setText("");
  }

  function close() {
    setOpen(false);
    setText("");
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-4 z-30 w-10 h-10 rounded-full bg-card border border-border text-text-muted hover:text-text-primary hover:border-purple-from/50 transition-all shadow-lg flex items-center justify-center text-lg font-bold select-none"
        aria-label="Report an issue"
        title="Report an issue"
      >
        ?
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) close(); }}
        >
          <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-5 space-y-4 shadow-2xl">
            <div className="flex justify-between items-center">
              <div>
                <h3 className="text-text-primary font-semibold">Report an issue</h3>
                <p className="text-text-muted text-xs mt-0.5">
                  Something break? Tell us — every report helps.
                </p>
              </div>
              <button
                onClick={close}
                className="text-text-muted hover:text-text-primary text-2xl leading-none w-8 h-8 flex items-center justify-center rounded-lg hover:bg-surface transition-colors"
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="What went wrong? Which video type? Any error message you saw?"
              rows={4}
              className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to focus:ring-1 focus:ring-purple-to resize-none text-sm"
              autoFocus
            />

            <div className="flex gap-3">
              <button
                onClick={submit}
                className="flex-1 gradient-btn text-white font-semibold py-2.5 rounded-xl text-sm hover:scale-[1.01] active:scale-[0.99] transition-transform"
              >
                Send report
              </button>
              <button
                onClick={close}
                className="px-4 py-2.5 border border-border text-text-muted hover:text-text-primary rounded-xl text-sm transition-colors"
              >
                Cancel
              </button>
            </div>

            <p className="text-text-muted/40 text-xs text-center">
              Opens your email app · or email{" "}
              <a
                href="mailto:irehan29@icloud.com"
                className="underline hover:text-text-muted transition-colors"
              >
                irehan29@icloud.com
              </a>{" "}
              directly
            </p>
          </div>
        </div>
      )}
    </>
  );
}
