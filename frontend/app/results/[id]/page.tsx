"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import VerdictBanner from "@/components/VerdictBanner";
import ScoreBar from "@/components/ScoreBar";
import FeedbackModal from "@/components/FeedbackModal";
import UpsellModal from "@/components/UpsellModal";
import { getAnalysis, claimAnalysis, seedConsentDecision, getAnalysisStatus, AnalysisOut } from "@/lib/api";
import { getToken } from "@/lib/auth";

function SeedConsentBanner({ analysis }: { analysis: AnalysisOut }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  function answer(allow: boolean, remember?: "yes" | "no") {
    setDismissed(true); // disappears on any click; the API call is best-effort
    seedConsentDecision(analysis.id, allow, remember).catch(() => {});
  }

  const views =
    analysis.actual_views != null
      ? `${analysis.actual_views.toLocaleString()} views`
      : "real engagement stats";

  return (
    <div className="bg-purple-from/5 border border-purple-to/30 rounded-2xl p-5 space-y-3">
      <div>
        <p className="text-text-primary font-semibold">🎯 Help other creators?</p>
        <p className="text-text-muted text-sm mt-1">
          Your post got {views} — Surge could use these stats as a benchmark to help
          score other creators&apos; videos. Your video is never stored.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => answer(true)}
          className="gradient-btn text-white font-semibold px-5 py-2 rounded-xl text-sm"
        >
          Yes, help others
        </button>
        <button
          onClick={() => answer(false)}
          className="border border-border text-text-muted hover:text-text-primary px-5 py-2 rounded-xl text-sm transition-colors"
        >
          No thanks
        </button>
        <span className="text-text-muted/60 text-xs">
          <button onClick={() => answer(true, "yes")} className="hover:text-text-muted underline">
            Always yes
          </button>
          {" / "}
          <button onClick={() => answer(false, "no")} className="hover:text-text-muted underline">
            Always no
          </button>
        </span>
      </div>
    </div>
  );
}

function ErrorScreen({ title, message }: { title: string; message: string }) {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 text-center gap-6">
      <div className="text-5xl">😕</div>
      <h1 className="text-2xl font-bold text-text-primary">{title}</h1>
      <p className="text-text-muted max-w-md">{message}</p>
      <Link
        href="/"
        className="gradient-btn text-white font-semibold px-6 py-3 rounded-xl"
      >
        Try again
      </Link>
    </main>
  );
}

export default function ResultsPage() {
  const params = useParams();
  const id = Array.isArray(params.id) ? params.id[0] : (params.id as string);

  const [analysis, setAnalysis] = useState<AnalysisOut | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "notfound" | "timeout">("loading");
  const [loadingText, setLoadingText] = useState("Loading your results…");
  const [showUpsell, setShowUpsell] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const token = getToken();
      let a = await getAnalysis(id, token);

      // If scores are absent, the analysis is still processing — poll until done.
      const isPending = (scores: AnalysisOut["scores_json"]) =>
        Object.keys(scores).length === 0 ||
        (scores.overall_score == null && !scores.error && !scores.locked);

      if (isPending(a.scores_json)) {
        if (!cancelled) setLoadingText("Still analyzing your video — this can take up to 60 seconds…");

        let timedOut = true;
        for (let i = 0; i < 100; i++) {
          await new Promise((r) => setTimeout(r, 3000));
          if (cancelled) return;

          const { status: pollStatus } = await getAnalysisStatus(Number(id));
          if (pollStatus === "complete" || pollStatus === "error") {
            a = await getAnalysis(id, token);
            timedOut = false;
            break;
          }
        }

        if (timedOut) {
          if (!cancelled) setStatus("timeout");
          return;
        }
      }

      // If the result is locked but the user is logged in, the analysis may
      // not have been claimed yet (e.g., a previous claim failed silently).
      // Attempt a claim now and re-fetch so the user gets the full view.
      if (a.scores_json.locked && token) {
        try {
          await claimAnalysis(id, token);
          a = await getAnalysis(id, token);
        } catch {
          // If claim is rejected (belongs to another account), keep the locked view.
        }
      }

      if (!cancelled) {
        setAnalysis(a);
        setStatus("ok");
      }
    }

    load().catch(() => {
      if (!cancelled) setStatus("notfound");
    });

    return () => {
      cancelled = true;
    };
  }, [id]);

  const locked = !!analysis?.scores_json.locked;

  // Auto-show the upsell modal once per analysis for anonymous (locked) views.
  useEffect(() => {
    if (!locked) return;
    const key = `upsell_seen_${id}`;
    if (sessionStorage.getItem(key)) return;
    const timer = setTimeout(() => {
      setShowUpsell(true);
      sessionStorage.setItem(key, "1");
    }, 800);
    return () => clearTimeout(timer);
  }, [locked, id]);

  if (status === "loading") {
    return (
      <main className="min-h-screen bg-background">
        <Nav />
        <div className="max-w-3xl mx-auto px-4 py-16 text-center text-text-muted">
          {loadingText}
        </div>
      </main>
    );
  }

  if (status === "timeout") {
    return (
      <ErrorScreen
        title="Analysis timed out"
        message="Analysis timed out. Please try again."
      />
    );
  }

  if (status === "notfound" || !analysis) {
    return (
      <ErrorScreen
        title="Analysis not found"
        message="Something went wrong loading your results."
      />
    );
  }

  const s = analysis.scores_json;

  if (s.error) {
    return (
      <ErrorScreen title="Analysis failed" message={s.analysis_summary} />
    );
  }

  const scores = [
    { label: "Overall Score",       score: s.overall_score },
    { label: "Hook Velocity",       score: s.hook_velocity },
    { label: "Cut Frequency",       score: s.cut_frequency },
    { label: "Text Scannability",   score: s.text_scannability },
    { label: "Curiosity Gap",       score: s.curiosity_gap },
    { label: "Audio-Visual Sync",   score: s.audio_visual_sync },
    { label: "Loop Seamlessness",   score: s.loop_seamlessness },
  ];

  const MODE_LABEL: Record<string, string> = {
    quick: "Lite",
    thinking: "Thinking",
    deep_thinking: "Deep — Personalized",
  };
  const modeLabel = MODE_LABEL[analysis.mode ?? "quick"] ?? MODE_LABEL.quick;

  return (
    <main className="min-h-screen bg-background">
      <Nav subtitle={analysis.niche} />

      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        {/* Effective-mode badge — reflects what actually ran, never overclaims */}
        <div className="flex justify-center">
          <span className="text-xs font-medium text-text-muted bg-card border border-border px-3 py-1 rounded-full">
            {modeLabel}
          </span>
        </div>

        {/* Verdict banner — always shown */}
        <VerdictBanner verdict={analysis.verdict} overallScore={s.overall_score ?? 0} />

        {locked ? (
          /* ---------- FREE TIER (anonymous): locked teaser ---------- */
          <>
            {/* Viral score callout */}
            {s.overall_score != null && (
              <div className="bg-card border border-border rounded-2xl p-5 flex items-center justify-between gap-4">
                <div>
                  <p className="text-text-muted text-xs uppercase tracking-widest font-semibold mb-1">
                    Viral Score
                  </p>
                  <p className="text-text-primary text-4xl font-extrabold tabular-nums">
                    {Math.round(s.overall_score * 10)}
                    <span className="text-text-muted text-xl font-normal">/100</span>
                  </p>
                </div>
                <div
                  className={`w-16 h-16 rounded-full flex items-center justify-center text-2xl font-extrabold border-4 ${
                    s.overall_score >= 7
                      ? "border-success text-success bg-success/10"
                      : s.overall_score >= 4
                      ? "border-warning text-warning bg-warning/10"
                      : "border-danger text-danger bg-danger/10"
                  }`}
                >
                  {s.overall_score >= 7 ? "🔥" : s.overall_score >= 4 ? "⚡" : "⚠️"}
                </div>
              </div>
            )}

            {/* First improvement — visible teaser */}
            {s.first_improvement && (
              <div className="bg-card border border-border rounded-2xl p-5">
                <p className="text-text-muted text-xs uppercase tracking-widest font-semibold mb-3">
                  Top issue detected
                </p>
                <div className="flex items-start gap-3">
                  <span className="text-danger mt-0.5 text-base flex-shrink-0">→</span>
                  <p className="text-text-primary text-sm leading-relaxed">
                    <span className="font-semibold">{s.first_improvement.area}:</span>{" "}
                    {s.first_improvement.problem}
                  </p>
                </div>
              </div>
            )}

            {/* Blurred remaining report + lock gate */}
            <div className="relative overflow-hidden rounded-2xl">
              <div className="space-y-3 blur-[6px] select-none pointer-events-none">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <div key={i} className="bg-card border border-border rounded-2xl p-5 h-[72px]" />
                ))}
              </div>
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-5 bg-gradient-to-b from-background/30 to-background/95 text-center px-6 py-10">
                <div className="text-3xl">🔒</div>
                <p className="text-text-primary font-bold text-lg max-w-xs">
                  Your video has {s.overall_score != null && s.overall_score < 5 ? "3" : "multiple"} critical flaws.
                  Create an account to unlock your full analysis report and see the exact timestamps.
                </p>
                <Link
                  href={`/signup?next=/results/${analysis.id}`}
                  className="gradient-btn text-white font-bold px-8 py-3.5 rounded-xl shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-transform text-base"
                >
                  Create free account
                </Link>
                <p className="text-text-muted/70 text-xs">Free forever · no credit card</p>
                <p className="text-text-muted text-xs">
                  Already have an account?{" "}
                  <Link href={`/login?next=/results/${analysis.id}`} className="text-purple-to hover:underline">
                    Log in
                  </Link>
                </p>
              </div>
            </div>

            <div className="text-center pb-4">
              <Link
                href="/"
                className="inline-block bg-card border border-border text-text-primary font-semibold px-8 py-3 rounded-xl hover:border-purple-to transition-colors"
              >
                Analyze another video →
              </Link>
            </div>
          </>
        ) : (
          /* ---------- FULL (logged in) ---------- */
          <>
            {/* Seed-pool consent banner (only when the user's setting is "ask"
                and a verified link is waiting on their decision) */}
            {analysis.pending_seed_consent && <SeedConsentBanner analysis={analysis} />}

            {/* Scores grid */}
            <div className="bg-card border border-border rounded-2xl p-6">
              <h2 className="text-text-primary font-semibold text-lg mb-5">
                Performance Scores
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {scores.map((sc, i) => (
                  <ScoreBar
                    key={sc.label}
                    label={sc.label}
                    score={sc.score}
                    animate={true}
                    delay={i * 100}
                  />
                ))}
              </div>
            </div>

            {/* Strengths + Improvements */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-success/5 border border-success/20 rounded-2xl p-5">
                <h3 className="text-success font-semibold mb-3 flex items-center gap-2">
                  <span>✅</span> Strengths
                </h3>
                <ul className="space-y-2">
                  {(s.strengths ?? []).map((str: string, i: number) => (
                    <li key={i} className="text-text-muted text-sm flex gap-2">
                      <span className="text-success mt-0.5">•</span>
                      <span>{str}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="bg-danger/5 border border-danger/20 rounded-2xl p-5">
                <h3 className="text-danger font-semibold mb-3 flex items-center gap-2">
                  <span>🔺</span> Improvements
                </h3>
                <ul className="space-y-2">
                  {(s.improvements ?? []).map((imp: string, i: number) => (
                    <li key={i} className="text-text-muted text-sm flex gap-2">
                      <span className="text-danger mt-0.5">→</span>
                      <span>{imp}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* CTA → full improvement plan */}
            <Link
              href={`/results/${analysis.id}/improve`}
              className="block rounded-2xl p-[1px] gradient-btn hover:scale-[1.01] active:scale-[0.99] transition-transform"
            >
              <div className="rounded-2xl bg-card px-6 py-5 flex items-center justify-between gap-4">
                <div>
                  <p className="text-text-primary font-bold text-lg">
                    Get your full improvement plan →
                  </p>
                  <p className="text-text-muted text-sm">
                    Prioritized fixes, hook &amp; caption rewrites, and your
                    projected score.
                  </p>
                </div>
                <span className="text-2xl flex-shrink-0">🚀</span>
              </div>
            </Link>

            {/* Summary */}
            <div className="bg-card border border-border rounded-2xl p-6">
              <h3 className="text-text-muted text-xs uppercase tracking-widest font-semibold mb-3">
                Analysis Summary
              </h3>
              <p className="text-text-primary leading-relaxed">
                {s.analysis_summary}
              </p>
            </div>

            {/* Submitted caption / bio */}
            {(analysis.caption || analysis.bio) && (
              <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
                <h3 className="text-text-muted text-xs uppercase tracking-widest font-semibold">
                  Analyzed alongside your video
                </h3>
                {analysis.caption && (
                  <div>
                    <p className="text-text-muted text-xs mb-1">Caption</p>
                    <p className="text-text-primary text-sm whitespace-pre-wrap">
                      {analysis.caption}
                    </p>
                  </div>
                )}
                {analysis.bio && (
                  <div>
                    <p className="text-text-muted text-xs mb-1">Profile bio</p>
                    <p className="text-text-primary text-sm whitespace-pre-wrap">
                      {analysis.bio}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Feedback */}
            <FeedbackModal analysisId={analysis.id} platform={analysis.platform} />

            {/* CTA */}
            <div className="text-center pb-4">
              <Link
                href="/"
                className="inline-block gradient-btn text-white font-semibold px-8 py-3 rounded-xl hover:scale-[1.02] active:scale-[0.98] transition-transform"
              >
                Analyze another video →
              </Link>
            </div>
          </>
        )}
      </div>

      {showUpsell && (
        <UpsellModal analysisId={analysis.id} onClose={() => setShowUpsell(false)} />
      )}
    </main>
  );
}
