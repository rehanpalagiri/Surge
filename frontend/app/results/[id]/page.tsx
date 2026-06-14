"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import VerdictBanner from "@/components/VerdictBanner";
import ScoreBar from "@/components/ScoreBar";
import FeedbackModal from "@/components/FeedbackModal";
import UpsellModal from "@/components/UpsellModal";
import { getAnalysis, claimAnalysis, seedConsentDecision, AnalysisOut } from "@/lib/api";
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
  const [status, setStatus] = useState<"loading" | "ok" | "notfound">("loading");
  const [showUpsell, setShowUpsell] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const token = getToken();
      let a = await getAnalysis(id, token);

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
          Loading your results…
        </div>
      </main>
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
    { label: "Overall Score", score: s.overall_score },
    { label: "Hook Strength", score: s.hook_strength },
    { label: "Pacing", score: s.pacing_score },
    { label: "Audio", score: s.audio_score },
    { label: "Captions", score: s.caption_score },
    { label: "Trend Alignment", score: s.trend_alignment },
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
        <VerdictBanner verdict={analysis.verdict} predictedViews={s.predicted_views} predictedLikes={s.predicted_likes} platform={analysis.platform ?? "tiktok"} />

        {locked ? (
          /* ---------- FREE TIER (anonymous): locked teaser ---------- */
          <>
            <div className="relative overflow-hidden rounded-2xl border border-border">
              {/* Blurred placeholder content */}
              <div className="p-6 space-y-5 blur-[6px] select-none pointer-events-none">
                <h2 className="text-text-primary font-semibold text-lg">
                  Performance Scores
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  {["Overall", "Hook", "Pacing", "Audio", "Captions", "Trend"].map(
                    (l, i) => (
                      <ScoreBar
                        key={l}
                        label={l}
                        score={[8, 6, 5, 7, 5, 6][i]}
                        animate={false}
                      />
                    )
                  )}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-success/5 border border-success/20 rounded-2xl p-5 h-28" />
                  <div className="bg-danger/5 border border-danger/20 rounded-2xl p-5 h-28" />
                </div>
              </div>

              {/* Unlock overlay */}
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-gradient-to-b from-background/50 to-background/80 text-center px-6">
                <p className="text-text-primary font-bold text-xl">
                  Your full breakdown is ready 🎉
                </p>
                <ul className="text-text-muted text-sm space-y-2 text-left">
                  {[
                    "All 6 performance scores, explained",
                    "Your strengths & priority fixes",
                    "Rewritten hook & caption",
                  ].map((item) => (
                    <li key={item} className="flex items-center gap-2.5">
                      <span className="text-success flex-shrink-0">✓</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  href={`/signup?next=/results/${analysis.id}`}
                  className="gradient-btn text-white font-semibold px-7 py-3 rounded-xl mt-1 shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-transform"
                >
                  Sign up free to unlock
                </Link>
                <p className="text-text-muted/70 text-xs">
                  Free forever · no credit card
                </p>
                <p className="text-text-muted text-xs">
                  Already have an account?{" "}
                  <Link
                    href={`/login?next=/results/${analysis.id}`}
                    className="text-purple-to hover:underline"
                  >
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
