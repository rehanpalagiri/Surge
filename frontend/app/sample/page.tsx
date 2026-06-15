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
  hook_strength: 9,
  pacing_score: 7,
  audio_score: 8,
  caption_score: 6,
  trend_alignment: 8,
  strengths: [
    "Hook is exceptional — the first 0.8 seconds create instant pattern interruption with an unexpected transformation cut that stops the scroll reflex.",
    "Audio layering is professional: trending sound selected at near-peak velocity, background music supports speech without competing with it.",
    "Trend alignment is strong — transformation-reveal formats in fitness are seeing 20–35% above-average save rates this week.",
  ],
  improvements: [
    "Caption is generic: 'gym motivation 💪 #fitness' won't surface in Explore. Rewrite to 'Why 99% of people never see results (it's not what you think)' to trigger curiosity clicks.",
    "Pacing sags at 0:12–0:18 — tighten this section to 3 seconds max to keep the momentum from the hook alive.",
    "No closing CTA — add 'Save this for your next training block' at the end to push save rate up by an estimated 15–25%.",
  ],
  analysis_summary:
    "This video has the raw ingredients to break through — a powerful hook, great audio instincts, and solid trend awareness. The biggest opportunity is the caption and the mid-video pacing drag. Fix those two and this is a realistic Explore-tab candidate. The transformation format is working; lean into it harder in the CTA.",
  improvement_plan: [
    {
      priority: "High",
      action: "Rewrite the caption",
      detail:
        "Replace 'gym motivation 💪 #fitness' with a curiosity-gap hook: 'Why 99% of gym-goers never actually change their body (it's not effort)'. Add 3–5 niche-specific hashtags (#calisthenics, #naturalbodybuilding) rather than broad ones.",
    },
    {
      priority: "High",
      action: "Trim the 0:12–0:18 section",
      detail:
        "Cut or speed-ramp the transition sequence in the middle third. The hook earns you ~2 seconds of audience patience — don't spend it on a slow reveal. Target: under 1.5 seconds for that cut.",
    },
    {
      priority: "Medium",
      action: "Add a closing CTA",
      detail:
        "End with text overlay: 'Save this for your next workout'. Save rate is the single highest-weight signal for the Explore algorithm in fitness content right now.",
    },
  ],
};

const SCORES = [
  { label: "Overall Score",   score: SAMPLE.overall_score },
  { label: "Hook Strength",   score: SAMPLE.hook_strength },
  { label: "Pacing",          score: SAMPLE.pacing_score },
  { label: "Audio",           score: SAMPLE.audio_score },
  { label: "Captions",        score: SAMPLE.caption_score },
  { label: "Trend Alignment", score: SAMPLE.trend_alignment },
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
          predictedViews={SAMPLE.predicted_views}
          predictedLikes={SAMPLE.predicted_likes}
          platform={SAMPLE.platform}
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
