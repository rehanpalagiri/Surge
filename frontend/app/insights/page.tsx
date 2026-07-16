"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import { Link2 } from "lucide-react";
import { getToken } from "@/lib/auth";
import { getCraftInsights, CraftInsights, CraftInsightPending } from "@/lib/api";

const DIMENSION_ORDER = [
  ["hook_velocity", "Hook"],
  ["cut_frequency", "Cuts"],
  ["text_scannability", "Text"],
  ["curiosity_gap", "Curiosity"],
  ["audio_visual_sync", "A/V Sync"],
  ["loop_seamlessness", "Ending"],
] as const;

const HORIZON_LABEL: Record<string, string> = {
  "24h": "24-hour", "7d": "7-day", "30d": "30-day",
};

function etaDateLabel(eta: string | null): string | null {
  if (!eta) return null;
  return new Date(eta).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function pendingMessage(p: CraftInsightPending): string {
  const etaStr = etaDateLabel(p.eta);
  if (p.reason === "instagram_no_views") {
    return "Instagram doesn't share view counts with us, so a like rate can't be computed for this post.";
  }
  if (p.reason === "low_views") {
    return etaStr
      ? `Verified, but still under the reliable-rate view floor — next check-in around ${etaStr}.`
      : "Verified, but still under the reliable-rate view floor.";
  }
  if (p.overdue) {
    return "Its check-in window has passed — this updates automatically within a day.";
  }
  const horizon = p.eta_horizon ? HORIZON_LABEL[p.eta_horizon] : null;
  return etaStr
    ? `Waiting for its ${horizon ?? "next"} check-in, around ${etaStr}.`
    : "Waiting on its next check-in.";
}

function PendingList({ pending, totalAnalyses }: { pending: CraftInsightPending[]; totalAnalyses: number }) {
  // "instagram_no_views" is a permanent provider limitation, not something still
  // processing — only show the spinner/"verifying" framing when at least one
  // post is actually waiting on a future check-in.
  const anyInProgress = pending.some((p) => p.reason !== "instagram_no_views");
  const title = anyInProgress ? "Verifying your linked posts" : "Like-rate insights aren't available yet";
  const subtitle = anyInProgress
    ? `You've linked ${pending.length === 1 ? "a post" : `${pending.length} posts`} — insights show up ` +
      "once its verified counts clear the same-age comparison window. Nothing to do here, this updates on its own."
    : "Instagram doesn't expose view counts through our provider, so a like rate can't be computed for the post(s) below yet.";

  return (
    <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
      <div className="flex items-center gap-2.5">
        {anyInProgress && <span className="pending-spinner text-accent-2 shrink-0" aria-hidden="true" />}
        <h2 className="text-text-primary font-semibold">{title}</h2>
      </div>
      <p className="text-text-muted text-sm leading-relaxed">{subtitle}</p>
      <ul className="space-y-3">
        {pending.map((p) => (
          <li key={p.analysis_id} className="border-t border-border/60 pt-3 first:border-0 first:pt-0">
            <Link
              href={`/results/${p.analysis_id}`}
              className="text-text-primary text-sm font-medium hover:text-accent"
            >
              {p.project_name || `${p.platform} post`}
            </Link>
            <p className="text-text-muted text-xs mt-0.5">{pendingMessage(p)}</p>
          </li>
        ))}
      </ul>
      {totalAnalyses > pending.length && (
        <p className="text-text-muted/70 text-xs border-t border-border pt-3">
          Link more posts from{" "}
          <Link href="/projects" className="text-accent hover:underline">your projects</Link> to build a
          bigger picture faster.
        </p>
      )}
    </div>
  );
}

function Notice({ text }: { text: string }) {
  return (
    <p className="text-text-muted/70 text-xs leading-relaxed border-t border-border pt-4">
      {text}
    </p>
  );
}

/* Small "n of N" progress toward the next honesty threshold. Informational,
   so it wears the ice-blue secondary accent — never the action citron. */
function ThresholdProgress({ have, need, label }: { have: number; need: number; label: string }) {
  return (
    <div className="space-y-1.5">
      <div className="h-1.5 rounded-full bg-border/60 overflow-hidden" role="presentation">
        <div
          className="h-full rounded-full bg-accent-2"
          style={{ width: `${Math.min(100, Math.round((have / need) * 100))}%` }}
        />
      </div>
      <p className="text-text-muted text-xs">{label}</p>
    </div>
  );
}

function ConfidenceChip({ text }: { text: string }) {
  return (
    <span className="shrink-0 text-[11px] font-semibold px-2.5 py-0.5 rounded-full text-accent-2 bg-accent-2/10 border border-accent-2/30">
      {text}
    </span>
  );
}

const scoreColor = (v: number | null) =>
  v == null ? "text-text-muted" : v >= 7 ? "text-success" : v >= 4 ? "text-warning" : "text-danger";

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
          <span className="pending-spinner text-accent" aria-hidden="true" />
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
          <Link href="/projects" className="text-accent hover:underline text-sm">Back to projects →</Link>
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

        {verified === 0 && data.pending.length > 0 ? (
          <PendingList pending={data.pending} totalAnalyses={data.total_analyses} />
        ) : verified === 0 ? (
          /* ── Empty: ghost the real view so linking has a visible payoff ── */
          <div className="relative">
            <div className="space-y-6 blur-[3px] opacity-50 pointer-events-none select-none" aria-hidden="true">
              <div className="bg-accent/5 border border-accent/30 rounded-2xl p-6 space-y-3">
                <h2 className="text-text-primary font-semibold">What your posts tend to land</h2>
                <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
                  <div>
                    <p className="text-3xl font-bold text-accent tabular-nums">4.1–6.8%</p>
                    <p className="text-text-muted text-xs mt-1">middle 50% of your like rates</p>
                  </div>
                  <div className="text-sm text-text-muted">
                    <p>median <span className="text-text-primary font-semibold tabular-nums">5.3%</span></p>
                    <p>range <span className="text-text-primary tabular-nums">2.9–8.4%</span></p>
                  </div>
                </div>
                <p className="text-text-muted text-xs">
                  Empirical spread across your verified posts — historical context, not a target or a promise.
                </p>
              </div>
              <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
                <h2 className="text-text-primary font-semibold">Which craft dimensions track your results</h2>
                <div className="space-y-3">
                  {[
                    { label: "Hook Velocity", high: "6.4%", low: "4.5%", delta: "1.9%", up: true },
                    { label: "Ending Strength", high: "6.1%", low: "4.9%", delta: "1.2%", up: true },
                    { label: "Text Scannability", high: "5.1%", low: "5.5%", delta: "0.4%", up: false },
                  ].map((row) => (
                    <div key={row.label} className="flex items-center justify-between gap-3 border-b border-border/60 pb-3 last:border-0 last:pb-0">
                      <div>
                        <p className="text-text-primary text-sm font-medium">{row.label}</p>
                        <p className="text-text-muted text-xs">
                          higher-scoring posts: <span className="text-text-primary tabular-nums">{row.high}</span>{" "}
                          vs <span className="text-text-primary tabular-nums">{row.low}</span>
                        </p>
                      </div>
                      <span className={`text-sm font-bold tabular-nums ${row.up ? "text-success" : "text-danger"}`}>
                        {row.up ? "▲" : "▼"}{row.delta}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="absolute inset-0 flex items-center justify-center px-4">
              <div className="bg-card/95 backdrop-blur-sm border border-border rounded-2xl p-8 text-center space-y-4 max-w-md shadow-xl">
                <Link2 className="h-8 w-8 mx-auto text-accent" aria-hidden="true" />
                <h2 className="text-text-primary font-semibold text-lg">Link a posted video to begin</h2>
                <p className="text-text-muted text-sm leading-relaxed">
                  Once you link posts and their verified view/like counts, this page shows how your
                  craft scores relate to what actually happened — grounded in your real numbers, never a guess.
                  {data.total_analyses > 0 && (
                    <> You have <strong className="text-text-primary">{data.total_analyses}</strong> {data.total_analyses === 1 ? "analysis" : "analyses"} ready to link.</>
                  )}
                </p>
                <Link href="/projects" className="gradient-btn inline-block text-white font-semibold px-6 py-2.5 rounded-xl text-sm">
                  Go to my projects →
                </Link>
                <p className="text-text-muted/70 text-[11px]">
                  The blurred numbers behind this are examples — yours will be real.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <>
            <p className="text-text-muted text-sm">
              Based on <strong className="text-text-primary">{verified}</strong> verified{" "}
              {verified === 1 ? "post" : "posts"} at the <strong className="text-text-primary">{horizonLabel}</strong> mark.
            </p>

            {/* ── Observed range (only when enough data) ── */}
            {data.observed_range.available ? (
              <div className="bg-accent/5 border border-accent/30 rounded-2xl p-6 space-y-3">
                <h2 className="text-text-primary font-semibold">What your posts tend to land</h2>
                <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
                  <div>
                    <p className="text-3xl font-bold text-accent tabular-nums">
                      {data.observed_range.p25}–{data.observed_range.p75}%
                    </p>
                    <p className="text-text-muted text-xs mt-1">middle 50% of your like rates</p>
                  </div>
                  <div className="text-sm text-text-muted">
                    <p>median <span className="text-text-primary font-semibold tabular-nums">{data.observed_range.median}%</span></p>
                    <p>range <span className="text-text-primary tabular-nums">{data.observed_range.min}–{data.observed_range.max}%</span></p>
                  </div>
                </div>
                <p className="text-text-muted text-xs">
                  Empirical spread across your {data.observed_range.n} verified posts — historical context, not a target or a promise.
                </p>
              </div>
            ) : data.observed_range.preliminary && verified === 1 ? (
              /* ── n = 1: the single-post comparison, honestly labeled ── */
              <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-text-primary font-semibold">Your first data point</h2>
                  <ConfidenceChip text="based on 1 post" />
                </div>
                <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
                  <div>
                    <p className="text-3xl font-bold text-accent tabular-nums">
                      {data.observed_range.preliminary.median}%
                    </p>
                    <p className="text-text-muted text-xs mt-1">observed like rate at the {horizonLabel} mark</p>
                  </div>
                </div>
                {/* Craft snapshot of that post, next to its real result */}
                {data.posts[0] && (
                  <div className="flex flex-wrap gap-2">
                    {DIMENSION_ORDER.map(([key, label]) => {
                      const v = data.posts[0].scores[key];
                      return (
                        <span
                          key={key}
                          className="text-xs px-2.5 py-1 rounded-lg bg-surface border border-border/60 text-text-muted"
                        >
                          {label}{" "}
                          <strong className={`tabular-nums ${scoreColor(v)}`}>
                            {v != null ? v.toFixed(0) : "—"}
                          </strong>
                        </span>
                      );
                    })}
                  </div>
                )}
                <p className="text-text-muted text-xs">
                  A single data point, not a pattern — historical context, never a promise.
                  This becomes your personal range as more posts link.
                </p>
                <ThresholdProgress
                  have={1}
                  need={data.observed_range.need}
                  label={`1 of ${data.observed_range.need} posts toward your reliable like-rate range`}
                />
              </div>
            ) : data.observed_range.preliminary ? (
              /* ── 2 ≤ n < 8: preliminary spread, low confidence ── */
              <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-text-primary font-semibold">What your posts land so far</h2>
                  <ConfidenceChip text={`based on ${data.observed_range.preliminary.n} posts · low confidence`} />
                </div>
                <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
                  <div>
                    <p className="text-3xl font-bold text-accent tabular-nums">
                      {data.observed_range.preliminary.median}%
                    </p>
                    <p className="text-text-muted text-xs mt-1">median like rate</p>
                  </div>
                  <div className="text-sm text-text-muted">
                    <p>
                      range{" "}
                      <span className="text-text-primary tabular-nums">
                        {data.observed_range.preliminary.min}–{data.observed_range.preliminary.max}%
                      </span>
                    </p>
                  </div>
                </div>
                <p className="text-text-muted text-xs">
                  Raw spread of your {data.observed_range.preliminary.n} verified posts — historical
                  context, not a target or a promise.
                </p>
                <ThresholdProgress
                  have={data.observed_range.have}
                  need={data.observed_range.need}
                  label={`${data.observed_range.have} of ${data.observed_range.need} posts toward your reliable like-rate range`}
                />
              </div>
            ) : null}

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
              <div className="bg-card border border-border rounded-2xl p-6 space-y-3">
                <h2 className="text-text-primary font-semibold">Which craft dimensions track your results</h2>
                <p className="text-text-muted text-sm">
                  Unlocks at {data.pattern_min} verified posts — the smallest sample where a
                  high-vs-low comparison is honest rather than noise dressed up as signal.
                </p>
                <ThresholdProgress
                  have={verified}
                  need={data.pattern_min}
                  label={`${verified} of ${data.pattern_min} posts toward your craft-vs-results patterns`}
                />
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
                        <Link href={`/results/${post.analysis_id}`} className="text-text-primary hover:text-accent">
                          {post.project_name || `${post.niche} post`}
                        </Link>
                      </td>
                      {DIMENSION_ORDER.map(([key]) => {
                        const v = post.scores[key];
                        return (
                          <td key={key} className={`text-center px-1.5 tabular-nums ${scoreColor(v)}`}>
                            {v != null ? v.toFixed(0) : "—"}
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
