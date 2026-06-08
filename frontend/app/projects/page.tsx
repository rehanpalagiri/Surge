"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { getMyAnalyses, deleteAnalysis, AnalysisSummary } from "@/lib/api";
import { getToken } from "@/lib/auth";

function verdictColor(verdict: string): string {
  if (verdict === "High potential") return "text-success";
  if (verdict === "Average potential") return "text-warning";
  return "text-danger";
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 7) return "text-success";
  if (score >= 5) return "text-warning";
  return "text-danger";
}

function groupByDate(analyses: AnalysisSummary[]): { label: string; items: AnalysisSummary[] }[] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);
  const startOfWeek = new Date(startOfToday);
  startOfWeek.setDate(startOfWeek.getDate() - 7);
  const startOfMonth = new Date(startOfToday);
  startOfMonth.setDate(startOfMonth.getDate() - 30);

  const groups: { label: string; items: AnalysisSummary[] }[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "This Week", items: [] },
    { label: "This Month", items: [] },
    { label: "Older", items: [] },
  ];

  for (const a of analyses) {
    const d = new Date(a.created_at);
    if (d >= startOfToday) groups[0].items.push(a);
    else if (d >= startOfYesterday) groups[1].items.push(a);
    else if (d >= startOfWeek) groups[2].items.push(a);
    else if (d >= startOfMonth) groups[3].items.push(a);
    else groups[4].items.push(a);
  }

  return groups.filter((g) => g.items.length > 0);
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

function ProjectCard({
  a,
  onDeleted,
}: {
  a: AnalysisSummary;
  onDeleted: (id: number) => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setDeleting(true);
    try {
      await deleteAnalysis(a.id, getToken());
      onDeleted(a.id);
    } catch {
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

  function handleCancelDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setConfirmDelete(false);
  }

  return (
    <div className="relative group">
      <Link
        href={`/results/${a.id}`}
        className="block bg-card border border-border rounded-2xl p-5 hover:border-purple-to transition-colors"
      >
        <div className="flex items-start justify-between mb-2 gap-2">
          <span className="text-text-primary font-semibold capitalize">
            {a.niche}
          </span>
          {a.predicted_views && (
            <span className="text-text-muted text-xs font-medium shrink-0">
              ~{a.predicted_views}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mb-1">
          <p className={`text-sm font-medium ${verdictColor(a.verdict)}`}>
            {a.verdict}
          </p>
          {a.overall_score !== null && (
            <span className={`text-xs font-bold ${scoreColor(a.overall_score)}`}>
              {a.overall_score}/10
            </span>
          )}
        </div>
        {a.caption_preview && (
          <p className="text-text-muted text-sm mt-2 line-clamp-2">
            {a.caption_preview}
          </p>
        )}
        <p className="text-text-muted text-xs mt-3">
          {new Date(a.created_at).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
          })}
          {a.actual_views !== null &&
            ` · ${a.actual_views.toLocaleString()} views`}
          {a.actual_likes !== null &&
            ` · ${a.actual_likes.toLocaleString()} likes`}
        </p>
      </Link>

      {/* Delete button — appears on hover */}
      {!confirmDelete ? (
        <button
          onClick={handleDelete}
          className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity bg-card border border-border text-text-muted hover:text-danger hover:border-danger rounded-lg px-2 py-1 text-xs"
        >
          Delete
        </button>
      ) : (
        <div className="absolute top-3 right-3 flex items-center gap-1 bg-card border border-danger rounded-lg px-2 py-1 shadow-lg">
          <span className="text-danger text-xs font-semibold mr-1">Sure?</span>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="text-danger text-xs font-bold hover:underline disabled:opacity-50"
          >
            {deleting ? "…" : "Yes"}
          </button>
          <span className="text-text-muted text-xs">·</span>
          <button
            onClick={handleCancelDelete}
            className="text-text-muted text-xs hover:text-text-primary"
          >
            No
          </button>
        </div>
      )}
    </div>
  );
}

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

  function handleDeleted(id: number) {
    setAnalyses((prev) => prev?.filter((a) => a.id !== id) ?? null);
  }

  const filtered = analyses?.filter((a) => a.platform === platform) ?? null;
  const cfg = PLATFORM_TABS.find((p) => p.id === platform)!;
  const groups = filtered ? groupByDate(filtered) : null;

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
          <div className="space-y-8">
            {groups!.map((group) => (
              <div key={group.label}>
                <h2 className="text-text-muted text-xs uppercase tracking-widest font-semibold mb-3">
                  {group.label}
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {group.items.map((a) => (
                    <ProjectCard key={a.id} a={a} onDeleted={handleDeleted} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
