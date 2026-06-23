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
import { track } from "@vercel/analytics";

const SCORE_DIMENSIONS = [
  { key: "overall_score",      label: "Overall Score" },
  { key: "hook_velocity",      label: "Hook Velocity" },
  { key: "cut_frequency",      label: "Cut Frequency" },
  { key: "text_scannability",  label: "Text Scannability" },
  { key: "curiosity_gap",      label: "Curiosity Gap" },
  { key: "audio_visual_sync",  label: "Audio-Visual Sync" },
  { key: "loop_seamlessness",  label: "Loop Seamlessness" },
] as const;

type ScoreKey = typeof SCORE_DIMENSIONS[number]["key"];

function ScoreComparison({ current, parent }: { current: AnalysisOut; parent: AnalysisOut }) {
  const cs = current.scores_json as unknown as Record<string, number>;
  const ps = parent.scores_json as unknown as Record<string, number>;

  return (
    <div className="bg-card border border-border rounded-2xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-text-primary font-semibold text-lg">Score Comparison</h2>
        <Link
          href={`/results/${parent.id}`}
          className="text-text-muted text-xs hover:text-text-primary underline"
        >
          View previous →
        </Link>
      </div>
      <div className="grid grid-cols-3 text-xs font-semibold text-text-muted uppercase tracking-widest mb-3 px-1">
        <span>Dimension</span>
        <span className="text-center">Before</span>
        <span className="text-center">After</span>
      </div>
      <div className="space-y-2">
        {SCORE_DIMENSIONS.map(({ key, label }) => {
          const prev = ps[key as ScoreKey] ?? null;
          const curr = cs[key as ScoreKey] ?? null;
          const delta = prev != null && curr != null ? curr - prev : null;
          return (
            <div key={key} className="grid grid-cols-3 items-center px-1 py-1.5 rounded-lg hover:bg-surface/50 transition-colors">
              <span className="text-text-muted text-sm">{label}</span>
              <span className="text-center text-text-muted text-sm tabular-nums">
                {prev != null ? prev.toFixed(1) : "—"}
              </span>
              <span className="text-center flex items-center justify-center gap-1.5">
                <span className={`text-sm font-semibold tabular-nums ${
                  curr == null ? "text-text-muted" :
                  curr >= 7 ? "text-success" :
                  curr >= 4 ? "text-warning" : "text-danger"
                }`}>
                  {curr != null ? curr.toFixed(1) : "—"}
                </span>
                {delta != null && Math.abs(delta) >= 0.05 && (
                  <span className={`text-xs font-bold ${delta > 0 ? "text-success" : "text-danger"}`}>
                    {delta > 0 ? "▲" : "▼"}{Math.abs(delta).toFixed(1)}
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-text-muted/60 text-xs mt-4 text-center">
        Compared to{" "}
        {new Date(parent.created_at).toLocaleDateString(undefined, {
          month: "short", day: "numeric", year: "numeric",
        })}
      </p>
    </div>
  );
}


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
  const [parentAnalysis, setParentAnalysis] = useState<AnalysisOut | null>(null);
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
        // Fetch the parent analysis for score comparison (best-effort, no error shown).
        if (a.parent_id && token) {
          getAnalysis(a.parent_id, token).then(setParentAnalysis).catch(() => {});
        }
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
      <ErrorScreen title="Analysis failed" message={s.error} />
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

  // Emotional teaser (owner only). Full lands/misses/amplify lives on the improve page.
  // Guard achieved_score — Gemini can omit/malform it (would render "undefined/10").
  const ea = s.emotional_analysis;
  const hasEmotional =
    !!ea && Array.isArray(ea.target_emotions) && ea.target_emotions.length > 0;
  const emoScore =
    ea && typeof ea.achieved_score === "number" && Number.isFinite(ea.achieved_score)
      ? ea.achieved_score
      : 0;
  const emoColor = emoScore >= 7 ? "text-success" : emoScore >= 4 ? "text-warning" : "text-danger";

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
                  onClick={() => track("signup_cta_clicked", { analysis_id: analysis.id, score: Math.round((s.overall_score ?? 0) * 10) })}
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

            <div className="flex justify-center pb-4">
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

            {/* Score comparison vs previous version */}
            {parentAnalysis && !parentAnalysis.scores_json.locked && (
              <ScoreComparison current={analysis} parent={parentAnalysis} />
            )}

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

            {/* Emotional impact — teaser (full breakdown on the improve page) */}
            {hasEmotional && ea && (
              <div className="bg-card border border-border rounded-2xl p-6">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h3 className="text-text-primary font-semibold flex items-center gap-2">
                    <span>❤️‍🔥</span> Emotional impact
                  </h3>
                  <span className={`text-sm font-bold ${emoColor}`}>{emoScore}/10</span>
                </div>
                <p className="text-text-muted text-xs uppercase tracking-wide mb-2">
                  Should make viewers feel
                </p>
                <div className="flex flex-wrap gap-2">
                  {ea.target_emotions.map((e: string, i: number) => (
                    <span
                      key={i}
                      className="text-xs font-medium bg-surface border border-border rounded-lg px-2.5 py-1 text-text-primary"
                    >
                      {e}
                    </span>
                  ))}
                </div>
                <p className="text-text-muted text-xs mt-3">
                  See what lands, what&apos;s missing, and how to amplify it in your full plan below.
                </p>
              </div>
            )}

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
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pb-4">
              <Link
                href={`/?parent=${analysis.id}&niche=${encodeURIComponent(analysis.niche)}&platform=${analysis.platform}`}
                className="inline-block gradient-btn text-white font-semibold px-8 py-3 rounded-xl hover:scale-[1.02] active:scale-[0.98] transition-transform"
              >
                🔄 Re-analyze this project
              </Link>
              <Link
                href="/"
                className="inline-block bg-card border border-border text-text-primary font-semibold px-8 py-3 rounded-xl hover:border-purple-to transition-colors"
              >
                Analyze a new video →
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
