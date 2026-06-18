"use client";

import Link from "next/link";
import Nav from "@/components/Nav";
import VerdictBanner from "@/components/VerdictBanner";
import ScoreBar from "@/components/ScoreBar";

const SAMPLE = {
  niche: "Fitness",
  platform: "tiktok" as const,
  mode: "Thinking",
  verdict: "High potential" as const,
  predicted_views: "180K–350K",
  predicted_likes: "12K–28K",
  overall_score: 8,
  hook_velocity: 9,
  cut_frequency: 7,
  text_scannability: 6,
  curiosity_gap: 8,
  audio_visual_sync: 8,
  loop_seamlessness: 4,
  strengths: [
    "Hook velocity is exceptional — transformation cut lands on frame 1 with bold text overlay, eliminating the viewer's reason to scroll before they consciously decide to.",
    "Curiosity gap is strong: opening line 'Most people train wrong for years and never know it' creates an immediate open loop that demands resolution.",
    "Audio-visual sync is tight throughout — every major cut lands on a beat drop or audio transient, making the pacing feel intentional and professional.",
  ],
  improvements: [
    "Loop seamlessness fails at the end — the sign-off 'hope this helped, follow for more' explicitly tells the viewer the video is over and triggers the scroll reflex. The rewatch multiplier is being thrown away.",
    "Text scannability drops at 0:08–0:14 — caption overlay appears in the bottom 20% of frame and will be covered by TikTok's description UI on most devices.",
    "Cut frequency sags at 0:12–0:18 — a 4.2-second static talking-head shot after the hook loses the attention the opening earned.",
  ],
  analysis_summary:
    "Strong hook and curiosity gap give this video a real shot at FYP distribution — the first 3 seconds do their job. The loop ending is the single biggest missed opportunity: replacing the sign-off with a callback to the opening hook could push rewatches up significantly, which is the metric TikTok weighs most. Fix the caption position and mid-video pacing drag and this is a legitimate Explore candidate.",
  improvement_plan: [
    {
      priority: "High",
      action: "Fix the loop ending",
      detail:
        "Delete 'hope this helped, follow for more.' Replace the final line with an open-ended callback to the hook: 'So the next time you think you're training hard enough...' — this pulls viewers back to the start and triggers the rewatch signal the algorithm responds to most.",
    },
    {
      priority: "High",
      action: "Move text out of the UI collision zone",
      detail:
        "At 0:08–0:14, your caption text sits in the bottom 20% of frame. On most devices, TikTok's username and description overlay will cover it entirely. Move all on-screen text to the center or upper third of the frame.",
    },
    {
      priority: "Medium",
      action: "Cut the 0:12–0:18 static hold",
      detail:
        "You hold a talking-head shot for 4.2 seconds with no cut, zoom, or B-roll. Insert a 1.2× digital zoom at the 3-second mark or cut to a B-roll clip to reset the viewer's attention clock before retention drops.",
    },
  ],
};

const SCORES = [
  { label: "Overall Score",     score: SAMPLE.overall_score },
  { label: "Hook Velocity",     score: SAMPLE.hook_velocity },
  { label: "Cut Frequency",     score: SAMPLE.cut_frequency },
  { label: "Text Scannability", score: SAMPLE.text_scannability },
  { label: "Curiosity Gap",     score: SAMPLE.curiosity_gap },
  { label: "Audio-Visual Sync", score: SAMPLE.audio_visual_sync },
  { label: "Loop Seamlessness", score: SAMPLE.loop_seamlessness },
];

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
      <div className="bg-purple-from/10 border-b border-purple-to/20 px-4 py-3 text-center text-sm text-text-muted">
        📋 This is a <span className="text-text-primary font-semibold">sample report</span> — the real thing is generated from your actual video.{" "}
        <Link href="/" className="text-purple-to hover:underline font-medium">
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
        <VerdictBanner
          verdict={SAMPLE.verdict}
          overallScore={SAMPLE.overall_score}
        />

        {/* Scores */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <h2 className="text-text-primary font-semibold text-lg mb-5">Performance Scores</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {SCORES.map((sc, i) => (
              <ScoreBar key={sc.label} label={sc.label} score={sc.score} animate delay={i * 100} />
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
              {SAMPLE.strengths.map((s, i) => (
                <li key={i} className="text-text-muted text-sm flex gap-2">
                  <span className="text-success mt-0.5 flex-shrink-0">•</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="bg-danger/5 border border-danger/20 rounded-2xl p-5">
            <h3 className="text-danger font-semibold mb-3 flex items-center gap-2">
              <span>🔺</span> Improvements
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
          <h3 className="text-text-primary font-semibold text-lg">Full Improvement Plan</h3>
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
            <p className="text-text-muted/50 text-xs">
              Already have an account?{" "}
              <Link href="/login" className="text-purple-to hover:underline">
                Log in
              </Link>
            </p>
          </div>
        </div>

        <div className="text-center pb-4">
          <Link href="/" className="text-text-muted text-sm hover:text-text-primary transition-colors">
            ← Back to Surge
          </Link>
        </div>
      </div>
    </main>
  );
}
