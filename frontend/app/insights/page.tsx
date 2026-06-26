"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import { getToken } from "@/lib/auth";
import { getCraftInsights, CraftInsights } from "@/lib/api";

const DIMENSION_ORDER = [
  ["hook_velocity", "Hook"],
  ["cut_frequency", "Cuts"],
  ["text_scannability", "Text"],
  ["curiosity_gap", "Curiosity"],
  ["audio_visual_sync", "A/V Sync"],
  ["loop_seamlessness", "Loop"],
] as const;

const HORIZON_LABEL: Record<string, string> = {
  "24h": "24-hour", "7d": "7-day", "30d": "30-day",
};

function Notice({ text }: { text: string }) {
  return (
    <p className="text-text-muted/70 text-xs leading-relaxed border-t border-border pt-4">
      {text}
    </p>
  );
}

export default function InsightsPage() {
  const router = useRouter();
  const [data, setData] = useState<CraftInsights | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login?next=/insights");
      return;
    }
    getCraftInsights()
      .then((d) => { setData(d); setStatus("ok"); })
      .catch(() => setStatus("error"));
  }, [router]);

  if (status === "loading") {
    return (
      <main className="min-h-screen bg-background">
        <Nav />
        <div className="max-w-3xl mx-auto px-4 py-24 flex flex-col items-center gap-3" role="status">
          <span className="pending-spinner text-purple-to" aria-hidden="true" />
          <p className="text-text-muted text-sm">Gathering your verified results…</p>
        </div>
      </main>
    );
  }

  if (status === "error" || !data) {
    return (
      <main className="min-h-screen bg-background">
        <Nav />
        <div className="max-w-3xl mx-auto px-4 py-24 text-center space-y-4">
          <p className="text-text-primary font-semibold">Couldn&apos;t load your insights.</p>
          <Link href="/projects" className="text-purple-to hover:underline text-sm">Back to projects →</Link>
        </div>
      </main>
    );
  }

  const verified = data.with_verified_outcome;
  const horizonLabel = data.horizon ? HORIZON_LABEL[data.horizon] : "";

  return (
    <main className="min-h-screen bg-background">
      <Nav />
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <header className="space-y-2">
          <h1 className="text-2xl font-bold text-text-primary">Craft vs. Your Results</h1>
          <p className="text-text-muted text-sm">
            How your craft assessments line up with the real, verified results on your own posts.
            Observed like rate (likes ÷ views), compared only at the same post age.
          </p>
        </header>

        {verified === 0 ? (
          /* ── Empty: drive the loop ── */
          <div className="bg-card border border-border rounded-2xl p-8 text-center space-y-4">
            <div className="text-4xl">🔗</div>
            <h2 className="text-text-primary font-semibold text-lg">Link a posted video to begin</h2>
            <p className="text-text-muted text-sm max-w-md mx-auto leading-relaxed">
              Once you link posts and their verified view/like counts, this page shows how your
              craft scores relate to what actually happened — grounded in your real numbers, never a guess.
              {data.total_analyses > 0 && (
                <> You have <strong className="text-text-primary">{data.total_analyses}</strong> {data.total_analyses === 1 ? "analysis" : "analyses"} ready to link.</>
              )}
            </p>
            <Link href="/projects" className="gradient-btn inline-block text-white font-semibold px-6 py-2.5 rounded-xl text-sm">
              Go to my projects →
            </Link>
          </div>
        ) : (
          <>
            <p className="text-text-muted text-sm">
              Based on <strong className="text-text-primary">{verified}</strong> verified{" "}
              {verified === 1 ? "post" : "posts"} at the <strong className="text-text-primary">{horizonLabel}</strong> mark.
            </p>

            {/* ── Forecast (only when enough data) ── */}
            {data.forecast.available ? (
              <div className="bg-purple-from/5 border border-purple-to/30 rounded-2xl p-6 space-y-3">
                <h2 className="text-text-primary font-semibold">What your posts tend to land</h2>
                <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
                  <div>
                    <p className="text-3xl font-bold text-purple-to tabular-nums">
                      {data.forecast.p25}–{data.forecast.p75}%
                    </p>
                    <p className="text-text-muted text-xs mt-1">middle 50% of your like rates</p>
                  </div>
                  <div className="text-sm text-text-muted">
                    <p>median <span className="text-text-primary font-semibold tabular-nums">{data.forecast.median}%</span></p>
                    <p>range <span className="text-text-primary tabular-nums">{data.forecast.min}–{data.forecast.max}%</span></p>
                  </div>
                </div>
                <p className="text-text-muted text-xs">
                  Empirical spread across your {data.forecast.n} verified posts — a realistic range to expect, not a target or a promise.
                </p>
              </div>
            ) : (
              <div className="bg-card border border-border rounded-2xl p-5 text-sm text-text-muted">
                Link <strong className="text-text-primary">{Math.max(0, data.forecast.need - data.forecast.have)}</strong> more
                verified {Math.max(0, data.forecast.need - data.forecast.have) === 1 ? "post" : "posts"} to unlock your expected like-rate range.
              </div>
            )}

            {/* ── Per-dimension patterns ── */}
            {data.patterns.length > 0 ? (
              <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
                <h2 className="text-text-primary font-semibold">Which craft dimensions track your results</h2>
                <div className="space-y-3">
                  {data.patterns.map((p) => {
                    const up = p.direction === "higher";
                    return (
                      <div key={p.dimension} className="flex items-center justify-between gap-3 border-b border-border/60 pb-3 last:border-0 last:pb-0">
                        <div>
                          <p className="text-text-primary text-sm font-medium">{p.label}</p>
                          <p className="text-text-muted text-xs">
                            higher-scoring posts: <span className="text-text-primary tabular-nums">{p.median_like_rate_high}%</span>{" "}
                            vs <span className="text-text-primary tabular-nums">{p.median_like_rate_low}%</span>{" "}
                            <span className="text-text-muted/60">(n {p.n_high}/{p.n_low})</span>
                          </p>
                        </div>
                        <span className={`text-sm font-bold tabular-nums ${up ? "text-success" : p.direction === "lower" ? "text-danger" : "text-text-muted"}`}>
                          {up ? "▲" : p.direction === "lower" ? "▼" : "—"}{Math.abs(p.delta)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="bg-card border border-border rounded-2xl p-5 text-sm text-text-muted">
                Link <strong className="text-text-primary">{Math.max(0, data.pattern_min - verified)}</strong> more
                verified {Math.max(0, data.pattern_min - verified) === 1 ? "post" : "posts"} to see which craft dimensions track your results.
              </div>
            )}

            {/* ── Per-post table ── */}
            <div className="bg-card border border-border rounded-2xl p-6 space-y-4 overflow-x-auto">
              <h2 className="text-text-primary font-semibold">Your verified posts</h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-text-muted text-xs uppercase tracking-wider">
                    <th className="text-left font-semibold pb-2 pr-3">Post</th>
                    {DIMENSION_ORDER.map(([, label]) => (
                      <th key={label} className="text-center font-semibold pb-2 px-1.5">{label}</th>
                    ))}
                    <th className="text-right font-semibold pb-2 pl-3">Like rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.posts.map((post) => (
                    <tr key={post.analysis_id} className="border-t border-border/60">
                      <td className="py-2.5 pr-3">
                        <Link href={`/results/${post.analysis_id}`} className="text-text-primary hover:text-purple-to">
                          {post.project_name || `${post.niche} post`}
                        </Link>
                      </td>
                      {DIMENSION_ORDER.map(([key]) => {
                        const v = post.scores[key];
                        const color = v >= 7 ? "text-success" : v >= 4 ? "text-warning" : "text-danger";
                        return (
                          <td key={key} className={`text-center px-1.5 tabular-nums ${color}`}>
                            {v?.toFixed?.(0) ?? "—"}
                          </td>
                        );
                      })}
                      <td className="text-right pl-3 font-semibold text-text-primary tabular-nums">{post.like_rate}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Notice text={data.notice} />
          </>
        )}
      </div>
    </main>
  );
}
