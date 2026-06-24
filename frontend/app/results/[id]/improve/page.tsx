"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import { getAnalysis, AnalysisOut, ImprovementItem } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { ImproveSkeleton } from "@/components/Skeleton";

function scoreColor(score: number): string {
  if (score >= 7) return "text-success";
  if (score >= 4) return "text-warning";
  return "text-danger";
}

function scoreBorder(score: number): string {
  if (score >= 7) return "border-success/30";
  if (score >= 4) return "border-warning/30";
  return "border-danger/30";
}

function scoreBarBg(score: number): string {
  if (score >= 7) return "bg-success";
  if (score >= 4) return "bg-warning";
  return "bg-danger";
}

export default function ImprovePage() {
  const params = useParams();
  const id = Array.isArray(params.id) ? params.id[0] : (params.id as string);
  const router = useRouter();

  const [analysis, setAnalysis] = useState<AnalysisOut | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "notfound">("loading");

  useEffect(() => {
    // Gate: anonymous users are redirected to sign up.
    if (!getToken()) {
      router.replace(`/signup?next=/results/${id}/improve`);
      return;
    }
    let cancelled = false;
    getAnalysis(id)
      .then((a) => {
        if (cancelled) return;
        setAnalysis(a);
        setStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setStatus("notfound");
      });
    return () => {
      cancelled = true;
    };
  }, [id, router]);

  if (status === "loading") {
    return (
      <main className="min-h-screen bg-background">
        <Nav />
        <div className="max-w-3xl mx-auto px-4 py-8">
          <ImproveSkeleton />
        </div>
      </main>
    );
  }

  if (status === "notfound" || !analysis) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center px-4 text-center gap-6">
        <div className="text-5xl">😕</div>
        <h1 className="text-2xl font-bold text-text-primary">Analysis not found</h1>
        <Link
          href="/"
          className="gradient-btn text-white font-semibold px-6 py-3 rounded-xl"
        >
          Try again
        </Link>
      </main>
    );
  }

  const s = analysis.scores_json;

  // Same error fallback as the results page.
  if (s.error) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center px-4 text-center gap-6">
        <div className="text-5xl">⚠️</div>
        <h1 className="text-2xl font-bold text-text-primary">Analysis failed</h1>
        <p className="text-text-muted max-w-md">{s.analysis_summary}</p>
        <Link
          href="/"
          className="gradient-btn text-white font-semibold px-6 py-3 rounded-xl"
        >
          Try again
        </Link>
      </main>
    );
  }

  const plan: ImprovementItem[] = Array.isArray(s.improvement_plan)
    ? [...s.improvement_plan].sort((a, b) => a.priority - b.priority).slice(0, 3)
    : [];
  const hasPlan = plan.length > 0;

  // Emotional impact. Gemini is told emotional_analysis is required, but the type marks it
  // optional and the model can omit/malform fields — so guard achieved_score (a missing or
  // non-numeric value would render "undefined/10" with a NaN-width bar).
  const ea = s.emotional_analysis;
  const hasEmotional =
    !!ea && Array.isArray(ea.target_emotions) && ea.target_emotions.length > 0;
  const emoScore =
    ea && typeof ea.achieved_score === "number" && Number.isFinite(ea.achieved_score)
      ? ea.achieved_score
      : 0;

  return (
    <main className="min-h-screen bg-background">
      <Nav subtitle={analysis.niche} />

      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl md:text-4xl font-extrabold">
            Your <span className="gradient-text">Next Experiment</span>
          </h1>
          <p className="text-text-muted">
            Editing hypotheses based on observable craft—not a forecast or causal guarantee.
          </p>
        </div>

        <div className="rounded-2xl p-[1px] gradient-btn">
          <div className="rounded-2xl bg-card px-6 py-5 space-y-3">
            <div>
              <p className="text-text-muted text-xs uppercase tracking-widest font-semibold">Change one variable</p>
              <p className="text-text-primary font-semibold mt-1">{s.recommended_experiment?.change ?? "Change one clearly defined editing variable."}</p>
            </div>
            <p className="text-text-muted text-sm"><span className="font-semibold">Keep constant:</span> {s.recommended_experiment?.keep_constant ?? "Keep the remaining major variables similar."}</p>
            <p className="text-text-muted text-sm"><span className="font-semibold">Observe:</span> {s.recommended_experiment?.observe ?? "Compare verified results at the same post age."}</p>
          </div>
        </div>

        {/* Prioritized action list */}
        {hasPlan ? (
          <div className="space-y-4">
            <h2 className="text-text-primary font-semibold text-lg">
              Prioritized actions
            </h2>
            {plan.map((item, i) => (
              <div
                key={i}
                className={`bg-card border rounded-2xl p-5 ${scoreBorder(item.current_score)}`}
              >
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 w-9 h-9 rounded-full gradient-btn text-white font-bold flex items-center justify-center">
                    {item.priority}
                  </div>
                  <div className="flex-1 space-y-3">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="text-text-primary font-semibold">
                        {item.area}
                      </span>
                      <span
                        className={`text-sm font-bold ${scoreColor(item.current_score)}`}
                      >
                        {item.current_score}/10
                      </span>
                    </div>
                    <div>
                      <p className="text-text-muted text-xs uppercase tracking-wide mb-0.5">
                        Problem
                      </p>
                      <p className="text-text-primary text-sm">{item.problem}</p>
                    </div>
                    <div>
                      <p className="text-text-muted text-xs uppercase tracking-wide mb-0.5">
                        Fix
                      </p>
                      <p className="text-text-primary text-sm">{item.fix}</p>
                    </div>
                    {item.pattern && (
                      <div className="flex items-center gap-2 pt-1">
                        <span className="text-text-muted text-xs uppercase tracking-wide">
                          Technique
                        </span>
                        <span className="text-xs font-medium bg-surface border border-border rounded-lg px-2 py-0.5 text-text-primary">
                          {item.pattern}
                        </span>
                      </div>
                    )}
                    {!item.pattern && item.example && (
                      <div className="bg-surface border border-border rounded-xl px-4 py-3">
                        <p className="text-text-muted text-xs uppercase tracking-wide mb-0.5">
                          Example
                        </p>
                        <p className="text-text-primary text-sm whitespace-pre-wrap">
                          {item.example}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          // Backward compatibility: older analyses only have `improvements`.
          <div className="space-y-4">
            <h2 className="text-text-primary font-semibold text-lg">
              Improvements
            </h2>
            {(s.improvements ?? []).map((imp, i) => (
              <div key={i} className="bg-card border border-border rounded-2xl p-5">
                <div className="flex items-start gap-3">
                  <span className="text-danger mt-0.5">→</span>
                  <p className="text-text-primary text-sm">{imp}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Rewrites — only when the richer data exists */}
        {hasPlan && s.hook_rewrite && (
          <div className="bg-card border border-border rounded-2xl p-6">
            <h3 className="text-text-primary font-semibold mb-2">
              Rewrite your hook
            </h3>
            <p className="text-text-primary text-sm whitespace-pre-wrap bg-surface border border-border rounded-xl px-4 py-3">
              {s.hook_rewrite}
            </p>
          </div>
        )}

        {hasPlan && s.caption_rewrite && (
          <div className="bg-card border border-border rounded-2xl p-6">
            <h3 className="text-text-primary font-semibold mb-2">
              Rewrite your caption
            </h3>
            <p className="text-text-primary text-sm whitespace-pre-wrap bg-surface border border-border rounded-xl px-4 py-3">
              {s.caption_rewrite}
            </p>
          </div>
        )}

        {/* Emotional impact */}
        {hasEmotional && ea && (
            <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <h3 className="text-text-primary font-semibold">
                  Emotional impact
                </h3>
                <span className={`text-sm font-bold ${scoreColor(emoScore)}`}>
                  {emoScore}/10
                </span>
              </div>

              <div>
                <p className="text-text-muted text-xs uppercase tracking-wide mb-1.5">
                  Should make viewers feel
                </p>
                <div className="flex flex-wrap gap-2">
                  {ea.target_emotions.map((e, i) => (
                    <span
                      key={i}
                      className="text-xs font-medium bg-surface border border-border rounded-lg px-2.5 py-1 text-text-primary"
                    >
                      {e}
                    </span>
                  ))}
                </div>
              </div>

              <div className="w-full h-2 rounded-full bg-surface overflow-hidden">
                <div
                  className={`h-full rounded-full ${scoreBarBg(emoScore)}`}
                  style={{ width: `${Math.max(0, Math.min(10, emoScore)) * 10}%` }}
                />
              </div>

              {ea.what_lands && (
                <div>
                  <p className="text-text-muted text-xs uppercase tracking-wide mb-0.5">
                    What lands
                  </p>
                  <p className="text-text-primary text-sm">{ea.what_lands}</p>
                </div>
              )}

              {ea.what_misses && (
                <div>
                  <p className="text-text-muted text-xs uppercase tracking-wide mb-0.5">
                    What&apos;s missing
                  </p>
                  <p className="text-text-primary text-sm">{ea.what_misses}</p>
                </div>
              )}

              {Array.isArray(ea.how_to_amplify) &&
                ea.how_to_amplify.length > 0 && (
                  <div>
                    <p className="text-text-muted text-xs uppercase tracking-wide mb-1">
                      How to amplify
                    </p>
                    <ul className="space-y-1.5">
                      {ea.how_to_amplify.map((t, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-2 text-text-primary text-sm"
                        >
                          <span className="text-purple-to mt-0.5">→</span>
                          {t}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
            </div>
          )}

        {/* Buttons */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2 pb-4">
          <Link
            href={`/results/${analysis.id}`}
            className="text-center bg-card border border-border text-text-primary font-semibold px-6 py-3 rounded-xl hover:border-purple-to transition-colors"
          >
            ← Back to results
          </Link>
          <Link
            href="/"
            className="text-center gradient-btn text-white font-semibold px-6 py-3 rounded-xl hover:scale-[1.02] active:scale-[0.98] transition-transform"
          >
            Analyze another video →
          </Link>
        </div>
      </div>
    </main>
  );
}
