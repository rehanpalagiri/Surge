"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { getMyAnalyses, AnalysisSummary } from "@/lib/api";
import { getToken } from "@/lib/auth";

function verdictColor(verdict: string): string {
  if (verdict === "High potential") return "text-success";
  if (verdict === "Average potential") return "text-warning";
  return "text-danger";
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 70) return "text-success";
  if (score >= 40) return "text-warning";
  return "text-danger";
}

type Platform = "tiktok" | "instagram";

const PLATFORM_TABS: {
  id: Platform;
  icon: string;
  label: string;
  textGradient: string;
  btnGradient: string;
}[] = [
  {
    id: "tiktok",
    icon: "🎵",
    label: "TikTok",
    textGradient: "gradient-text-tiktok",
    btnGradient: "gradient-btn-tiktok",
  },
  {
    id: "instagram",
    icon: "📸",
    label: "Instagram",
    textGradient: "gradient-text-instagram",
    btnGradient: "gradient-btn-instagram",
  },
];

export default function ProjectsPage() {
  const router = useRouter();
  const [analyses, setAnalyses] = useState<AnalysisSummary[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [platform, setPlatform] = useState<Platform>("tiktok");

  const load = () => {
    const token = getToken();
    if (!token) {
      router.replace("/login?next=/projects");
      return;
    }
    setAnalyses(null);
    setLoadFailed(false);
    getMyAnalyses(token)
      .then(setAnalyses)
      .catch(() => setLoadFailed(true));
  };

  useEffect(load, [router]);

  const filtered = analyses?.filter((a) => a.platform === platform) ?? null;
  const cfg = PLATFORM_TABS.find((p) => p.id === platform)!;

  return (
    <main className="min-h-screen bg-background">
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <div>
          <h1 className="text-3xl font-extrabold">
            Your <span className={cfg.textGradient}>Past Projects</span>
          </h1>
          <p className="text-text-muted mt-1">
            Every video you&apos;ve analyzed, saved to your account.
          </p>
        </div>

        {/* Platform Switcher */}
        <div className="flex justify-center">
          <div className="flex bg-card border border-border rounded-2xl p-1 gap-1">
            {PLATFORM_TABS.map((p) => (
              <button
                key={p.id}
                onClick={() => setPlatform(p.id)}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                  platform === p.id
                    ? `${p.btnGradient} text-white shadow-sm`
                    : "text-text-muted hover:text-text-primary"
                }`}
              >
                <span>{p.icon}</span>
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {loadFailed ? (
          <div className="bg-card border border-border rounded-2xl p-10 text-center">
            <div className="text-4xl mb-3">🔄</div>
            <p className="text-text-primary font-semibold">
              Couldn&apos;t reach the server
            </p>
            <p className="text-text-muted text-sm mt-1 mb-5">
              The backend may still be waking up — give it a moment and try again.
            </p>
            <button
              onClick={load}
              className="inline-block gradient-btn text-white font-semibold px-6 py-3 rounded-xl"
            >
              Retry
            </button>
          </div>
        ) : filtered === null ? (
          <p className="text-text-muted">Loading…</p>
        ) : filtered.length === 0 ? (
          <div className="bg-card border border-border rounded-2xl p-10 text-center">
            <div className="text-4xl mb-3">🎬</div>
            <p className="text-text-primary font-semibold">No projects yet</p>
            <p className="text-text-muted text-sm mt-1 mb-5">
              Analyze your first {platform === "tiktok" ? "TikTok" : "Reel"} to see it here.
            </p>
            <Link
              href="/"
              className={`inline-block ${cfg.btnGradient} text-white font-semibold px-6 py-3 rounded-xl`}
            >
              Analyze a video →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filtered.map((a) => (
              <Link
                key={a.id}
                href={`/results/${a.id}`}
                className="bg-card border border-border rounded-2xl p-5 hover:border-purple-to transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-text-primary font-semibold capitalize">
                    {a.niche}
                  </span>
                  {a.overall_score !== null && (
                    <span className={`font-bold ${scoreColor(a.overall_score)}`}>
                      {a.overall_score}/100
                    </span>
                  )}
                </div>
                <p className={`text-sm font-medium ${verdictColor(a.verdict)}`}>
                  {a.verdict}
                </p>
                {a.caption_preview && (
                  <p className="text-text-muted text-sm mt-2 line-clamp-2">
                    {a.caption_preview}
                  </p>
                )}
                <p className="text-text-muted text-xs mt-3">
                  {new Date(a.created_at).toLocaleDateString()}
                  {a.actual_views !== null &&
                    ` · ${a.actual_views.toLocaleString()} views`}
                  {a.actual_likes !== null &&
                    ` · ${a.actual_likes.toLocaleString()} likes`}
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
