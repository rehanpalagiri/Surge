"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { getMyAnalyses, deleteAnalysis, linkTikTokVideo, apiErrorDetail, AnalysisSummary } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { ProjectsSkeleton } from "@/components/Skeleton";
import PlatformTabs from "@/components/PlatformTabs";
import { ArrowUpRight, CalendarDays, Link2, RefreshCw, Trash2, Video } from "lucide-react";

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
      className="project-link-cta group w-full text-left"
    >
      <span className="relative z-10 flex min-w-0 items-center gap-3">
        <span className="grid h-11 w-11 flex-shrink-0 place-items-center rounded-xl border border-purple-to/25 bg-purple-from/15 text-purple-300 transition-transform group-hover:-translate-y-0.5 group-hover:scale-105">
          <Link2 className="h-5 w-5" strokeWidth={1.8} />
        </span>
        <span className="min-w-0">
          <span className="mb-0.5 block text-[10px] font-bold uppercase tracking-[0.18em] text-purple-300">Posted it?</span>
          <span className="block text-sm font-bold text-white">{title}</span>
          <span className="mt-0.5 block text-[11px] leading-relaxed text-zinc-400">
            Connect the post, start tracking results, and earn +1 analysis
          </span>
        </span>
      </span>
      <span className="relative z-10 grid h-8 w-8 flex-shrink-0 place-items-center rounded-full bg-purple-500 text-white shadow-lg shadow-purple-950/40 transition-transform group-hover:translate-x-1">
        <ArrowUpRight className="h-4 w-4" />
      </span>
    </button>
  );
}

type Platform = "tiktok" | "instagram";

const PLATFORM_TABS: {
  id: Platform;
  // TikTok uses its iconic glitch (white text, offset red+cyan shadow) instead
  // of the old cyan→red gradient; Instagram keeps its brand gradient.
  textGradient: string;
  btnGradient: string;
}[] = [
  {
    id: "tiktok",
    textGradient: "tiktok-glitch",
    btnGradient: "gradient-btn-tiktok",
  },
  {
    id: "instagram",
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
          className="motion-pop flex flex-col gap-2 sm:flex-row"
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
          className="motion-pop flex flex-col gap-2 sm:flex-row"
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

  const projectName = a.project_name?.trim() || `${a.niche || "Untitled"} project`;
  const updateUrl = `/?parent=${a.id}&niche=${encodeURIComponent(a.niche)}&platform=${a.platform}&project=${encodeURIComponent(projectName)}`;
  const needsLink = !a.video_url;

  return (
    <article className={`project-card-reactive group ${needsLink ? "needs-link" : ""}`}>
      <Link href={`/results/${a.id}`} className="relative z-10 block p-5 pb-4">
        <div className="mb-4 flex items-start justify-between gap-3 pr-10">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-xl border border-white/5 bg-white/[0.035] text-purple-300">
              <Video className="h-5 w-5" strokeWidth={1.6} />
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-base font-bold text-white">{projectName}</h2>
              <p className="mt-0.5 truncate text-xs capitalize text-zinc-500">{a.niche || "General"}</p>
            </div>
          </div>
          {needsLink && (
            <span className="rounded-full border border-purple-to/25 bg-purple-from/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-purple-300">
              Needs link
            </span>
          )}
        </div>
        <div className="mb-1 flex items-center gap-3">
          <p className={`text-sm font-medium ${verdictColor(a.verdict)}`}>
            {a.verdict}
          </p>
          {a.parent_id != null && (
            <span className="rounded-full bg-purple-from/10 px-2 py-0.5 text-[10px] font-semibold text-purple-300">Re-analyzed</span>
          )}
        </div>
        {a.caption_preview && (
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-zinc-400">
            {a.caption_preview}
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-white/5 pt-3 text-xs text-zinc-500">
          <span className="inline-flex items-center gap-1.5">
            <CalendarDays className="h-3.5 w-3.5" />
            {new Date(a.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
          </span>
          {a.actual_views !== null && <span>{a.actual_views.toLocaleString()} views</span>}
          {a.actual_likes !== null && <span>{a.actual_likes.toLocaleString()} likes</span>}
        </div>
      </Link>

      <div className="relative z-10 px-5 pb-4">
        <Link
          href={updateUrl}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted hover:border-purple-to/50 hover:text-text-primary"
          onClick={(e) => e.stopPropagation()}
        >
          <RefreshCw className="h-3.5 w-3.5" /> Re-analyze
        </Link>
      </div>

      {a.platform === "tiktok" && <TikTokStatsRow a={a} onUpdated={onUpdated} />}
      {a.platform === "instagram" && <InstagramStatsRow a={a} onUpdated={onUpdated} />}

      {/* Delete button — appears on hover */}
      {!confirmDelete ? (
        <button
          onClick={handleDelete}
          aria-label={`Delete ${projectName}`}
          className="absolute right-3 top-3 z-20 grid h-8 w-8 place-items-center rounded-lg border border-border bg-card text-text-muted opacity-100 hover:border-danger hover:text-danger sm:opacity-0 sm:group-hover:opacity-100"
        >
          <Trash2 className="h-3.5 w-3.5" />
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
    </article>
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
  const filtered = allForPlatform
    ?.filter((a) => !supersededIds.has(a.id))
    .sort((a, b) => {
      const linkPriority = Number(Boolean(a.video_url)) - Number(Boolean(b.video_url));
      if (linkPriority !== 0) return linkPriority;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    }) ?? null;

  const cfg = PLATFORM_TABS.find((p) => p.id === platform)!;

  return (
    <main className="min-h-screen bg-background">
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <div>
          <h1 className="text-3xl font-extrabold">
            Your <span className={cfg.textGradient}>Video Projects</span>
          </h1>
          <p className="text-text-muted mt-1">
            Projects waiting for a post link appear first, followed by your newest work.
          </p>
        </div>

        {/* Platform Switcher */}
        <div className="flex justify-center">
          <PlatformTabs value={platform} onChange={setPlatform} />
        </div>

        {loadFailed ? (
          <div className="bg-card border border-border rounded-2xl p-10 text-center">
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
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {filtered.map((a) => (
              <ProjectCard
                key={a.id}
                a={a}
                onDeleted={handleDeleted}
                onUpdated={handleUpdated}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
