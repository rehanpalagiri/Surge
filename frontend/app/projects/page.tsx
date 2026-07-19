"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { getMyAnalyses, deleteAnalysis, AnalysisSummary } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { ProjectsSkeleton } from "@/components/Skeleton";
import { verdictDisplay } from "@/lib/verdicts";
import PlatformTabs from "@/components/PlatformTabs";
import { CalendarDays, Eye, Trash2, Video } from "lucide-react";
import PostLinkCard from "@/components/PostLinkCard";

type Platform = "tiktok" | "instagram";

const PLATFORM_TABS: {
  id: Platform;
  // Brand treatments from the globals.css brand layer: chromatic glitch for
  // TikTok, purple→yellow gradient for Instagram (headings are large enough
  // for AA; dense contexts use the solid fallbacks instead).
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

  function handleTrashClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setConfirmDelete((v) => !v);
  }

  async function handleConfirmDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
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
  const needsLink = !a.video_url;

  return (
    <article className={`project-card-reactive group flex flex-col ${needsLink ? "needs-link" : ""}`}>
      <Link href={`/results/${a.id}`} className="relative z-10 block flex-1 p-5 pb-4">
        <div className="mb-4 flex items-start justify-between gap-3 pr-10">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-xl border border-border bg-surface text-accent">
              <Video className="h-5 w-5" strokeWidth={1.6} />
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-base font-bold text-text-primary">{projectName}</h2>
              <p className="mt-0.5 truncate text-xs capitalize text-text-muted">{a.niche || "General"}</p>
            </div>
          </div>
          {needsLink && (
            <span
              title="No post linked yet — use “Did you post this?” below to track real stats"
              className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-text-muted/50" />
              Not linked
            </span>
          )}
        </div>
        <div className="mb-1 flex items-center gap-3">
          <p className={`text-sm font-medium ${verdictDisplay(a.verdict).textClass}`}>
            {verdictDisplay(a.verdict).label}
          </p>
          {a.parent_id != null && (
            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold text-accent">Re-analyzed</span>
          )}
        </div>
        {a.caption_preview && (
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-text-muted">
            {a.caption_preview}
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3 text-xs text-text-muted">
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
          href={`/results/${a.id}`}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted hover:border-accent/50 hover:text-text-primary"
          onClick={(e) => e.stopPropagation()}
        >
          <Eye className="h-3.5 w-3.5" /> See analysis
        </Link>
      </div>

      {(a.platform === "tiktok" || a.platform === "instagram") && (
        <PostLinkCard
          id={a.id}
          platform={a.platform}
          videoUrl={a.video_url}
          countsFetchedAt={a.counts_fetched_at}
          onUpdated={onUpdated}
        />
      )}

      {/* Delete button — appears on hover; confirmation drops down below it so it
          never collides with the "Not linked" badge sharing the top-right corner. */}
      <button
        onClick={handleTrashClick}
        aria-label={confirmDelete ? "Cancel delete" : `Delete ${projectName}`}
        aria-expanded={confirmDelete}
        className={`absolute right-3 top-3 z-20 grid h-8 w-8 place-items-center rounded-lg border bg-card text-text-muted transition-colors ${
          confirmDelete
            ? "border-danger text-danger opacity-100"
            : "border-border opacity-100 hover:border-danger hover:text-danger sm:opacity-0 sm:group-hover:opacity-100"
        }`}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
      {confirmDelete && (
        <div className="absolute right-3 top-12 z-30 flex flex-col gap-2 rounded-lg border border-danger bg-card px-3 py-2 shadow-lg motion-pop">
          <span className="whitespace-nowrap text-xs font-semibold text-text-primary">
            Delete this project?
          </span>
          <div className="flex items-center justify-end gap-3">
            <button
              onClick={handleCancelDelete}
              className="text-xs font-medium text-text-muted hover:text-text-primary"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirmDelete}
              disabled={deleting}
              className="text-xs font-bold text-danger hover:underline disabled:opacity-50"
            >
              {deleting ? "…" : "Delete"}
            </button>
          </div>
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
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    ?? null;

  const cfg = PLATFORM_TABS.find((p) => p.id === platform)!;

  return (
    <main className="min-h-screen bg-background">
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <div>
          <h1 className="text-3xl font-extrabold">
            Your{" "}
            <span
              className={cfg.textGradient}
              data-text={platform === "tiktok" ? "TikTok Projects" : undefined}
            >
              {platform === "tiktok" ? "TikTok Projects" : "Instagram Reels"}
            </span>
          </h1>
          <p className="text-text-muted mt-1">
            Your newest projects appear at the top.
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
