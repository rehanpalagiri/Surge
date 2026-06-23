"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getToken } from "@/lib/auth";
import { getMyAnalyses, AnalysisSummary } from "@/lib/api";

const LS_PROMPT_KEY = "viraliq_link_prompt_shown";
const LS_QUESTIONS_KEY = "viraliq_any_questions_shown";
const SS_SESSION_KEY = "viraliq_session_active";

// Pages where we never interrupt the user
const AUTH_PAGES = ["/login", "/signup", "/forgot-password", "/reset-password", "/onboarding"];

type ModalState = "idle" | "link" | "questions" | "hidden";

export default function LinkPromptModal() {
  const [state, setState] = useState<ModalState>("idle");
  const [unlinked, setUnlinked] = useState<AnalysisSummary[]>([]);
  const pathname = usePathname();

  useEffect(() => {
    if (AUTH_PAGES.some((p) => pathname.startsWith(p))) {
      setState("hidden");
      return;
    }

    const token = getToken();
    if (!token) {
      setState("hidden");
      return;
    }

    const promptShown = localStorage.getItem(LS_PROMPT_KEY);
    const questionsShown = localStorage.getItem(LS_QUESTIONS_KEY);
    const sessionActive = sessionStorage.getItem(SS_SESSION_KEY);

    // Mark this browser session as active so "any questions?" only shows once per visit
    sessionStorage.setItem(SS_SESSION_KEY, "1");

    if (promptShown && !questionsShown && !sessionActive) {
      // They've seen the link prompt before, this is a fresh session, haven't seen "any questions?" yet
      setState("questions");
      return;
    }

    if (!promptShown) {
      // Check if they have TikTok analyses older than 24 h with no linked video
      const cutoff = Date.now() - 24 * 60 * 60 * 1000;
      getMyAnalyses(token)
        .then((analyses) => {
          const eligible = analyses.filter(
            (a) =>
              a.platform === "tiktok" &&
              !a.video_url &&
              new Date(a.created_at).getTime() < cutoff
          );
          if (eligible.length > 0) {
            setUnlinked(eligible.slice(0, 3));
            setState("link");
          } else {
            setState("hidden");
          }
        })
        .catch(() => setState("hidden"));
      return;
    }

    setState("hidden");
  }, [pathname]);

  function dismissLink() {
    localStorage.setItem(LS_PROMPT_KEY, Date.now().toString());
    setState("hidden");
  }

  function dismissQuestions() {
    localStorage.setItem(LS_QUESTIONS_KEY, "1");
    setState("hidden");
  }

  if (state === "idle" || state === "hidden") return null;

  /* ─── "Any questions?" toast — bottom-right, subtle ─── */
  if (state === "questions") {
    return (
      <div className="fixed bottom-20 right-4 z-50 max-w-xs w-full sm:max-w-sm animate-fade-in">
        <div className="relative rounded-2xl p-[1.5px] bg-gradient-to-r from-purple-600 to-pink-500 shadow-2xl">
          <div className="rounded-2xl bg-card px-4 py-4">
            <button
              onClick={dismissQuestions}
              aria-label="Dismiss"
              className="absolute top-2.5 right-3 text-text-muted hover:text-text-primary text-xl leading-none"
            >
              ×
            </button>
            <p className="text-sm font-bold text-text-primary mb-1 pr-5">
              👋 Welcome back!
            </p>
            <p className="text-sm text-text-muted leading-relaxed">
              Any questions about your results? Reply to any Surge email — we read every one.
            </p>
          </div>
        </div>
      </div>
    );
  }

  /* ─── Link-prompt modal ─── */
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4 bg-black/70 backdrop-blur-sm"
      onClick={dismissLink}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="relative w-full max-w-md rounded-2xl p-[1.5px] gradient-btn shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rounded-2xl bg-card px-7 py-8">
          {/* Close */}
          <button
            onClick={dismissLink}
            aria-label="Close"
            className="absolute top-3 right-4 text-text-muted hover:text-text-primary text-2xl leading-none"
          >
            ×
          </button>

          <div className="text-center mb-5">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-purple-600/20 text-3xl mb-4">
              📊
            </div>
            <h2 className="text-2xl font-extrabold text-text-primary leading-tight mb-2">
              How did your videos actually do?
            </h2>
            <p className="text-text-muted leading-relaxed text-sm">
              You&apos;ve posted these — link them to pull in real views &amp; likes and see if Surge called it right.
            </p>
          </div>

          {/* Unlinked project list */}
          {unlinked.length > 0 && (
            <div className="bg-surface border border-border rounded-xl divide-y divide-border mb-6">
              {unlinked.map((a) => (
                <div key={a.id} className="flex items-center justify-between px-4 py-3 gap-3">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-base shrink-0">🎵</span>
                    <span className="text-sm font-semibold text-text-primary capitalize truncate">
                      {a.niche}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                        a.verdict === "High potential"
                          ? "bg-success/10 text-success"
                          : a.verdict === "Average potential"
                          ? "bg-warning/10 text-warning"
                          : "bg-danger/10 text-danger"
                      }`}
                    >
                      {a.verdict}
                    </span>
                    <span className="text-text-muted text-xs">
                      {new Date(a.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-col gap-3">
            <Link
              href="/projects"
              onClick={dismissLink}
              className="gradient-btn text-white font-bold py-3 rounded-xl text-center hover:scale-[1.02] active:scale-[0.98] transition-transform block"
            >
              Add links on My Projects →
            </Link>
            <button
              onClick={dismissLink}
              className="text-text-muted hover:text-text-primary text-sm py-1 text-center transition-colors"
            >
              Maybe later
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
