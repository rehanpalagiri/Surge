"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import { getAnalysis, AnalysisOut, ImprovementItem } from "@/lib/api";
import { getToken } from "@/lib/auth";

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

  if (status === "loading" || !analysis) {
    return (
      <main className="min-h-screen bg-background">
        <Nav />
        <div className="max-w-3xl mx-auto px-4 py-16 text-center text-text-muted">
          {status === "notfound" ? "Analysis not found." : "Loading…"}
        </div>
      </main>
    );
  }

  if (status === "notfound") {
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
    ? [...s.improvement_plan].sort((a, b) => a.priority - b.priority)
    : [];
  const hasPlan = plan.length > 0;
  const hasProjection = !!(s.projected_verdict || s.projected_views);

  return (
    <main className="min-h-screen bg-background">
      <Nav subtitle={analysis.niche} />

      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl md:text-4xl font-extrabold">
            Your <span className="gradient-text">Improvement Plan</span>
          </h1>
          <p className="text-text-muted">
            Current score{" "}
            <span className={`font-bold ${scoreColor(s.overall_score)}`}>
              {s.overall_score}/10
            </span>{" "}
            · Verdict{" "}
            <span className="text-text-primary font-semibold">{s.verdict}</span>
          </p>
        </div>

        {/* Projected callout */}
        {hasProjection && (
          <div className="rounded-2xl p-[1px] gradient-btn">
            <div className="rounded-2xl bg-card px-6 py-5 text-center">
              <p className="text-text-muted text-sm uppercase tracking-widest font-semibold mb-1">
                Apply this plan →
              </p>
              <p className="text-xl font-bold text-text-primary">
                {s.projected_verdict && (
                  <span className="gradient-text">{s.projected_verdict}</span>
                )}
                {s.projected_verdict && s.projected_views && " · "}
                {s.projected_views}
              </p>
            </div>
          </div>
        )}

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
                    {item.example && (
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
            <h3 className="text-text-primary font-semibold mb-2 flex items-center gap-2">
              <span>🎬</span> Rewrite your hook
            </h3>
            <p className="text-text-primary text-sm whitespace-pre-wrap bg-surface border border-border rounded-xl px-4 py-3">
              {s.hook_rewrite}
            </p>
          </div>
        )}

        {hasPlan && s.caption_rewrite && (
          <div className="bg-card border border-border rounded-2xl p-6">
            <h3 className="text-text-primary font-semibold mb-2 flex items-center gap-2">
              <span>✍️</span> Rewrite your caption
            </h3>
            <p className="text-text-primary text-sm whitespace-pre-wrap bg-surface border border-border rounded-xl px-4 py-3">
              {s.caption_rewrite}
            </p>
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
