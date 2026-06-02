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

export default function ProjectsPage() {
  const router = useRouter();
  const [analyses, setAnalyses] = useState<AnalysisSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login?next=/projects");
      return;
    }
    getMyAnalyses(token)
      .then(setAnalyses)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load projects");
        setAnalyses([]);
      });
  }, [router]);

  return (
    <main className="min-h-screen bg-background">
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <div>
          <h1 className="text-3xl font-extrabold">
            Your <span className="gradient-text">Past Projects</span>
          </h1>
          <p className="text-text-muted mt-1">
            Every video you&apos;ve analyzed, saved to your account.
          </p>
        </div>

        {error && <p className="text-danger text-sm">{error}</p>}

        {analyses === null ? (
          <p className="text-text-muted">Loading…</p>
        ) : analyses.length === 0 ? (
          <div className="bg-card border border-border rounded-2xl p-10 text-center">
            <div className="text-4xl mb-3">🎬</div>
            <p className="text-text-primary font-semibold">No projects yet</p>
            <p className="text-text-muted text-sm mt-1 mb-5">
              Analyze your first video to see it here.
            </p>
            <Link
              href="/"
              className="inline-block gradient-btn text-white font-semibold px-6 py-3 rounded-xl"
            >
              Analyze a video →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {analyses.map((a) => (
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
                    ` · ${a.actual_views.toLocaleString()} actual views`}
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
