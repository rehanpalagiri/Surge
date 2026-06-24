"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { getMyAnalyses, deleteAnalysis, linkTikTokVideo, apiErrorDetail, AnalysisSummary } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { ProjectsSkeleton } from "@/components/Skeleton";

function verdictColor(verdict: string): string {
  if (verdict === "Strong craft" || verdict === "High potential") return "text-success";
  if (verdict === "Developing craft" || verdict === "Average potential") return "text-warning";
  return "text-danger";
}

// Collapsed CTA inviting the user to link a posted video/Reel. Same card for both
// platforms — only the headline differs.
function LinkCtaButton({ title, onClick }: { title: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center justify-between gap-3 bg-purple-from/10 border border-purple-to/40 hover:border-purple-to rounded-xl px-4 py-3 text-left transition-colors group"
    >
      <span className="flex items-center gap-2.5 min-w-0">
        <span className="text-lg flex-shrink-0">📊</span>
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-text-primary">{title}</span>
          <span className="block text-[11px] text-text-muted">
            Compare the review with real stats + earn 1 bonus analysis (up to 10)
          </span>
        </span>
      </span>
      <span className="text-purple-to font-bold flex-shrink-0 group-hover:translate-x-0.5 transition-transform">→</span>
    </button>
  );
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

function TikTokStatsRow({
  a,
  onUpdated,
}: {
  a: AnalysisSummary;
  onUpdated: (id: number, patch: Partial<AnalysisSummary>) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function fetchStats(url?: string) {
    setBusy(true);
    setError("");
    try {
      const updated = await linkTikTokVideo(a.id, url);
      onUpdated(a.id, {
        actual_views: updated.actual_views,
        actual_likes: updated.actual_likes,
        video_url: updated.video_url,
        counts_fetched_at: updated.counts_fetched_at,
      });
      setExpanded(false);
      setLink("");
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Couldn't fetch stats — try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="px-5 pb-4" aria-busy={busy}>
      {a.video_url ? (
        <button
          onClick={() => fetchStats()}
          disabled={busy}
          className="text-xs font-medium text-text-muted hover:text-text-primary border border-border hover:border-purple-from/50 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
        >
          {busy && <span className="pending-spinner mr-1.5 align-[-0.1em]" aria-hidden="true" />}
          {busy ? "Refreshing…" : "↻ Capture current TikTok stats"}
        </button>
      ) : !expanded ? (
        <LinkCtaButton title="Did you post this? Track real stats" onClick={() => setExpanded(true)} />
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (link.trim()) fetchStats(link.trim());
          }}
          className="flex gap-2"
        >
          <input
            type="url"
            autoFocus
            placeholder="https://www.tiktok.com/@you/video/…"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            className="flex-1 min-w-0 bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
          />
          <button
            type="submit"
            disabled={busy || !link.trim()}
            className="gradient-btn text-white text-xs font-semibold px-3 py-1.5 rounded-lg disabled:opacity-50 whitespace-nowrap"
          >
            {busy ? "…" : "Fetch"}
          </button>
          <button
            type="button"
            onClick={() => { setExpanded(false); setError(""); }}
            className="text-text-muted text-xs hover:text-text-primary"
          >
            ✕
          </button>
        </form>
      )}
      <p className="text-[11px] text-text-muted mt-2">
        Best captured near 24 hours, 7 days, and 30 days after posting.
      </p>
      {error && <p className="text-danger text-xs mt-1.5">{error}</p>}
    </div>
  );
}

function InstagramStatsRow({
  a,
  onUpdated,
}: {
  a: AnalysisSummary;
  onUpdated: (id: number, patch: Partial<AnalysisSummary>) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [link, setLink] = useState("");
  const [captureAge, setCaptureAge] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function fetchStats(url?: string) {
    if (!captureAge) {
      setError("Choose the Reel's age for this capture.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await linkTikTokVideo(a.id, url, Number(captureAge));
      onUpdated(a.id, {
        actual_likes: updated.actual_likes,
        video_url: updated.video_url,
        counts_fetched_at: updated.counts_fetched_at,
      });
      setExpanded(false);
      setLink("");
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Couldn't fetch stats — try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="px-5 pb-4" aria-busy={busy}>
      {a.video_url && !expanded ? (
        <button
          onClick={() => { setLink(a.video_url || ""); setExpanded(true); }}
          disabled={busy}
          className="text-xs font-medium text-text-muted hover:text-text-primary border border-border hover:border-purple-from/50 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
        >
          {busy && <span className="pending-spinner mr-1.5 align-[-0.1em]" aria-hidden="true" />}
          {busy ? "Refreshing…" : "↻ Capture current Instagram likes"}
        </button>
      ) : !expanded ? (
        <LinkCtaButton title="Did you post this Reel? Track real likes" onClick={() => setExpanded(true)} />
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (link.trim()) fetchStats(link.trim());
          }}
          className="flex gap-2"
        >
          <select
            value={captureAge}
            onChange={(e) => setCaptureAge(e.target.value)}
            className="min-w-0 bg-surface border border-border rounded-lg px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:border-purple-to"
            required
          >
            <option value="">Capture age</option>
            <option value="24">24 hours</option>
            <option value="168">7 days</option>
            <option value="720">30 days</option>
          </select>
          <input
            type="url"
            autoFocus
            placeholder="https://www.instagram.com/reel/…"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            className="flex-1 min-w-0 bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
          />
          <button
            type="submit"
            disabled={busy || !link.trim()}
            className="gradient-btn text-white text-xs font-semibold px-3 py-1.5 rounded-lg disabled:opacity-50 whitespace-nowrap"
          >
            {busy ? "…" : "Fetch"}
          </button>
          <button
            type="button"
            onClick={() => { setExpanded(false); setError(""); }}
            className="text-text-muted text-xs hover:text-text-primary"
          >
            ✕
          </button>
        </form>
      )}
      <p className="text-[11px] text-text-muted mt-2">
        Instagram likes are recorded as observations; Surge does not infer reach from them.
      </p>
      {error && <p className="text-danger text-xs mt-1.5">{error}</p>}
    </div>
  );
}

function ProjectCard({
  a,
  onDeleted,
  onUpdated,
}: {
  a: AnalysisSummary;
  onDeleted: (id: number) => void;
  onUpdated: (id: number, patch: Partial<AnalysisSummary>) => void;
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

  const reanalyzeUrl = `/?parent=${a.id}&niche=${encodeURIComponent(a.niche)}&platform=${a.platform}`;

  return (
    <div className="relative group bg-card border border-border rounded-2xl hover:border-purple-to transition-colors">
      <Link href={`/results/${a.id}`} className="block p-5 pb-3">
        <div className="flex items-start justify-between mb-2 gap-2">
          <span className="text-text-primary font-semibold capitalize">
            {a.niche}
          </span>
        </div>
        <div className="flex items-center gap-3 mb-1">
          <p className={`text-sm font-medium ${verdictColor(a.verdict)}`}>
            {a.verdict}
          </p>
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
          {(a.actual_views !== null || a.actual_likes !== null) && " · latest capture:"}
          {a.actual_views !== null &&
            ` ${a.actual_views.toLocaleString()} views`}
          {a.actual_likes !== null &&
            ` ${a.actual_views !== null ? "· " : ""}${a.actual_likes.toLocaleString()} likes`}
          {a.parent_id != null && (
            <span className="ml-2 text-purple-to font-medium">↺ Re-analyzed</span>
          )}
        </p>
      </Link>

      {/* Re-analyze button */}
      <div className="px-5 pb-4">
        <Link
          href={reanalyzeUrl}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-text-muted hover:text-text-primary border border-border hover:border-purple-to/50 rounded-lg px-3 py-1.5 transition-colors"
          onClick={(e) => e.stopPropagation()}
        >
          🔄 Re-analyze
        </Link>
      </div>

      {a.platform === "tiktok" && <TikTokStatsRow a={a} onUpdated={onUpdated} />}
      {a.platform === "instagram" && <InstagramStatsRow a={a} onUpdated={onUpdated} />}

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

  function handleUpdated(id: number, patch: Partial<AnalysisSummary>) {
    setAnalyses((prev) =>
      prev?.map((a) => (a.id === id ? { ...a, ...patch } : a)) ?? null
    );
  }

  const allForPlatform = analyses?.filter((a) => a.platform === platform) ?? null;

  // Identify superseded analyses: those whose ID appears as parent_id of another.
  // Only show the latest version of each lineage (leaf nodes).
  const supersededIds = new Set(
    (allForPlatform ?? []).map((a) => a.parent_id).filter((id): id is number => id != null)
  );
  const filtered = allForPlatform?.filter((a) => !supersededIds.has(a.id)) ?? null;

  const cfg = PLATFORM_TABS.find((p) => p.id === platform)!;
  const groups = filtered ? groupByDate(filtered) : null;

  return (
    <main className="min-h-screen bg-background">
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <div>
          <h1 className="text-3xl font-extrabold">
            Your <span className={cfg.textGradient}>Video Experiments</span>
          </h1>
          <p className="text-text-muted mt-1">
            Craft reviews and observed post results, kept separate so each post can teach you something.
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
          <ProjectsSkeleton />
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
                    <ProjectCard
                      key={a.id}
                      a={a}
                      onDeleted={handleDeleted}
                      onUpdated={handleUpdated}
                    />
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
