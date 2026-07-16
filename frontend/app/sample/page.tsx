"use client";

import Link from "next/link";
import Nav from "@/components/Nav";
import VerdictBanner from "@/components/VerdictBanner";
import ScoreBar from "@/components/ScoreBar";
import { SAMPLE_REPORT as SAMPLE, SAMPLE_SCORES as SCORES } from "@/lib/sampleReport";

const PRIORITY_COLOR: Record<string, string> = {
  High:   "text-danger border-danger/30 bg-danger/5",
  Medium: "text-warning border-warning/30 bg-warning/5",
  Low:    "text-success border-success/30 bg-success/5",
};

export default function SamplePage() {
  return (
    <main className="min-h-screen bg-background">
      <Nav />

      {/* Sample banner */}
      <div className="bg-accent/10 border-b border-accent/20 px-4 py-3 text-center text-sm text-text-muted">
        This is a <span className="text-text-primary font-semibold">sample report</span> — the real thing is generated from your actual video.{" "}
        <Link href="/" className="text-accent hover:underline font-medium">
          Try it with your video →
        </Link>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        {/* Mode badge */}
        <div className="flex justify-center">
          <span className="text-xs font-medium text-text-muted bg-card border border-border px-3 py-1 rounded-full">
            {SAMPLE.mode} · {SAMPLE.niche}
          </span>
        </div>

        {/* Verdict */}
        <VerdictBanner verdict={SAMPLE.verdict} />

        {/* Scores */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <h2 className="text-text-primary font-semibold text-lg mb-1">AI-Assessed Craft Dimensions</h2>
          <p className="text-text-muted text-xs mb-5">These are subjective craft assessments, not measured audience behavior.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {SCORES.map((sc, i) => (
              <ScoreBar key={sc.label} label={sc.label} score={sc.score} animate delay={i * 100} />
            ))}
          </div>
        </div>

        {/* Strengths + Improvements */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-success/5 border border-success/20 rounded-2xl p-5">
            <h3 className="text-success font-semibold mb-3">
              Strengths
            </h3>
            <ul className="space-y-2">
              {SAMPLE.strengths.map((s, i) => (
                <li key={i} className="text-text-muted text-sm flex gap-2">
                  <span className="text-success mt-0.5 flex-shrink-0">•</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="bg-danger/5 border border-danger/20 rounded-2xl p-5">
            <h3 className="text-danger font-semibold mb-3">
              Improvements
            </h3>
            <ul className="space-y-2">
              {SAMPLE.improvements.map((imp, i) => (
                <li key={i} className="text-text-muted text-sm flex gap-2">
                  <span className="text-danger mt-0.5 flex-shrink-0">→</span>
                  <span>{imp}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Improvement plan */}
        <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
          <h3 className="text-text-primary font-semibold text-lg">Editing hypotheses</h3>
          <div className="space-y-3">
            {SAMPLE.improvement_plan.map((item, i) => (
              <div key={i} className={`border rounded-xl p-4 ${PRIORITY_COLOR[item.priority]}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-xs font-bold uppercase tracking-wide px-2 py-0.5 rounded-full border ${PRIORITY_COLOR[item.priority]}`}>
                    {item.priority}
                  </span>
                  <span className="text-text-primary font-semibold text-sm">{item.action}</span>
                </div>
                <p className="text-text-muted text-sm">{item.detail}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
          <div>
            <h3 className="text-text-primary font-semibold text-lg">Observed results after posting</h3>
            <p className="text-text-muted text-sm mt-1">Example 24-hour snapshot. This is separate from the pre-post craft review.</p>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-surface rounded-xl p-3"><p className="text-text-primary font-bold">18,420</p><p className="text-text-muted text-xs">views</p></div>
            <div className="bg-surface rounded-xl p-3"><p className="text-text-primary font-bold">1,326</p><p className="text-text-muted text-xs">likes</p></div>
            <div className="bg-surface rounded-xl p-3"><p className="text-accent font-bold">7.20%</p><p className="text-text-muted text-xs">observed like rate</p></div>
          </div>
          <p className="text-text-muted text-xs">This difference is observational. It does not prove that a recommended edit caused the result.</p>
        </div>

        {/* Analysis summary */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <h3 className="text-text-muted text-xs uppercase tracking-widest font-semibold mb-3">
            Analysis Summary
          </h3>
          <p className="text-text-primary leading-relaxed">{SAMPLE.analysis_summary}</p>
        </div>

        {/* CTA */}
        <div className="rounded-2xl p-[1px] gradient-btn">
          <div className="rounded-2xl bg-card px-6 py-6 text-center space-y-3">
            <p className="text-text-primary font-bold text-xl">
              Get this for your own video
            </p>
            <p className="text-text-muted text-sm">
              Upload any TikTok or Instagram Reel and get your full breakdown in under a minute — free.
            </p>
            <Link
              href="/signup"
              className="inline-block gradient-btn text-white font-bold px-8 py-3 rounded-xl hover:scale-[1.02] active:scale-[0.98] transition-transform mt-1"
            >
              Create free account →
            </Link>
          </div>
        </div>

        <div className="text-center pb-4">
          <Link href="/" className="text-text-muted text-sm hover:text-text-primary transition-colors">
            ← Back to CraftLint
          </Link>
        </div>
      </div>
    </main>
  );
}
