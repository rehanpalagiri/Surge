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

const CONFETTI_PARTICLES: Array<{ color: string; tx: number; ty: number; r: number }> = [
  { color: "#a855f7", tx:   0, ty: -72, r: 120 },
  { color: "#ec4899", tx:  36, ty: -62, r: 210 },
  { color: "#fbbf24", tx:  60, ty: -36, r:  45 },
  { color: "#34d399", tx:  70, ty:   0, r: 300 },
  { color: "#60a5fa", tx:  60, ty:  36, r: 150 },
  { color: "#fb923c", tx:  36, ty:  60, r:  90 },
  { color: "#a855f7", tx:   0, ty:  70, r: 270 },
  { color: "#ec4899", tx: -36, ty:  60, r:  30 },
  { color: "#fbbf24", tx: -60, ty:  36, r: 200 },
  { color: "#34d399", tx: -70, ty:   0, r:  60 },
  { color: "#60a5fa", tx: -60, ty: -36, r: 320 },
  { color: "#fb923c", tx: -36, ty: -62, r: 170 },
];

const TIKTOK_HOW_TO = [
  "Open TikTok and find the video you just posted.",
  "Tap the Share arrow on the right side of the screen.",
  'Tap "Copy link" from the share sheet.',
  "Come back here and paste it in the box above.",
];

const INSTAGRAM_HOW_TO = [
  "Open Instagram and find your Reel.",
  "Tap the ⋯ (three dots) below or at the top of the post.",
  'Tap "Copy link".',
  "Come back here and paste it in the box above.",
];

type PostLinkPhase = "idle" | "celebrate" | "linking";

function PostLinkRow({
  a,
  platform,
  onUpdated,
}: {
  a: AnalysisSummary;
  platform: "tiktok" | "instagram";
  onUpdated: (id: number, patch: Partial<AnalysisSummary>) => void;
}) {
  const [phase, setPhase] = useState<PostLinkPhase>("idle");
  const [link, setLink] = useState("");
  const [captureAge, setCaptureAge] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showHowTo, setShowHowTo] = useState(false);
  const howTo = platform === "tiktok" ? TIKTOK_HOW_TO : INSTAGRAM_HOW_TO;

  function handlePostedClick() {
    setPhase("celebrate");
    setTimeout(() => setPhase("linking"), 1500);
  }

  async function fetchStats(url?: string) {
    if (platform === "instagram" && !captureAge && url !== undefined) {
      setError("Choose the Reel's age for this capture.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await linkTikTokVideo(
        a.id,
        url,
        platform === "instagram" && url !== undefined ? Number(captureAge) : undefined,
      );
      onUpdated(a.id, {
        actual_views: updated.actual_views,
        actual_likes: updated.actual_likes,
        video_url: updated.video_url,
        counts_fetched_at: updated.counts_fetched_at,
      });
      setPhase("idle");
      setLink("");
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Couldn't fetch stats — try again."));
    } finally {
      setBusy(false);
    }
  }

  // Already linked — TikTok refreshes in-place; Instagram re-opens form
  if (a.video_url && phase === "idle") {
    return (
      <div className="px-5 pb-4 space-y-2">
        <button
          onClick={() => {
            if (platform === "tiktok") {
              fetchStats(undefined);
            } else {
              setLink(a.video_url || "");
              setPhase("linking");
            }
          }}
          disabled={busy}
          className="text-xs font-medium text-text-muted hover:text-text-primary border border-border hover:border-purple-from/50 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
        >
          {busy && <span className="pending-spinner mr-1.5 align-[-0.1em]" aria-hidden="true" />}
          {busy
            ? "Refreshing…"
            : platform === "tiktok"
            ? "↻ Capture current TikTok stats"
            : "↻ Capture current Instagram likes"}
        </button>
        {platform === "instagram" && (
          <p className="text-[11px] text-text-muted">
            Instagram likes are recorded as observations; Surge does not infer reach from them.
          </p>
        )}
        {error && <p className="text-danger text-xs">{error}</p>}
      </div>
    );
  }

  // Celebration burst
  if (phase === "celebrate") {
    return (
      <div className="px-5 pb-5 flex flex-col items-center gap-2 py-5">
        <div className="relative flex justify-center items-center w-20 h-20">
          {CONFETTI_PARTICLES.map((p, i) => (
            <span
              key={i}
              className="absolute rounded-sm"
              style={{
                width: 10,
                height: 10,
                backgroundColor: p.color,
                "--tx": `${p.tx}px`,
                "--ty": `${p.ty}px`,
                "--r": `${p.r}deg`,
                animation: `confetti-particle 0.85s ${i * 40}ms cubic-bezier(0.1, 0.8, 0.3, 1) forwards`,
              } as React.CSSProperties}
            />
          ))}
          <span className="text-4xl relative z-10 select-none">🚀</span>
        </div>
        <p className="text-base font-bold text-white">You shipped it!</p>
        <p className="text-sm text-zinc-400">Let&apos;s capture those results…</p>
      </div>
    );
  }

  // Link form (phase === "linking" or not-yet-linked idle)
  if (phase === "linking") {
    const placeholder =
      platform === "tiktok"
        ? "https://www.tiktok.com/@you/video/…"
        : "https://www.instagram.com/reel/…";
    return (
      <div className="px-5 pb-4 space-y-2.5 motion-pop" aria-busy={busy}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (link.trim()) fetchStats(link.trim());
          }}
          className="flex flex-col gap-2 sm:flex-row"
        >
          {platform === "instagram" && (
            <select
              value={captureAge}
              onChange={(e) => setCaptureAge(e.target.value)}
              className="bg-surface border border-border rounded-lg px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:border-purple-to"
              required
            >
              <option value="">Capture age</option>
              <option value="24">24 hours</option>
              <option value="168">7 days</option>
              <option value="720">30 days</option>
            </select>
          )}
          <input
            type="url"
            autoFocus
            placeholder={placeholder}
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
            onClick={() => { setPhase("idle"); setError(""); setShowHowTo(false); }}
            className="text-text-muted text-xs hover:text-text-primary"
          >
            ✕
          </button>
        </form>
        {error && <p className="text-danger text-xs">{error}</p>}
        {platform === "instagram" && !error && (
          <p className="text-[11px] text-text-muted">
            Instagram likes are recorded as observations; Surge does not infer reach from them.
          </p>
        )}
        <button
          type="button"
          onClick={() => setShowHowTo((v) => !v)}
          className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors hover:underline underline-offset-2"
        >
          {showHowTo
            ? "Hide tutorial ↑"
            : `Don't know how to find the ${platform === "tiktok" ? "TikTok" : "Instagram"} link? ↓`}
        </button>
        {showHowTo && (
          <ol className="space-y-2 pt-0.5 motion-pop">
            {howTo.map((step, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <span className="flex-shrink-0 h-5 w-5 grid place-items-center rounded-full bg-purple-from/20 text-purple-300 text-[10px] font-bold">
                  {i + 1}
                </span>
                <p className="text-[11px] text-zinc-400 leading-relaxed pt-0.5">{step}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    );
  }

  // Idle, not yet linked
  return (
    <div className="px-5 pb-4">
      <button
        type="button"
        onClick={handlePostedClick}
        className="project-link-cta group w-full text-left"
      >
        <span className="relative z-10 flex min-w-0 items-center gap-3">
          <span className="grid h-11 w-11 flex-shrink-0 place-items-center rounded-xl border border-purple-to/25 bg-purple-from/15 text-purple-300 transition-transform group-hover:-translate-y-0.5 group-hover:scale-105">
            <Link2 className="h-5 w-5" strokeWidth={1.8} />
          </span>
          <span className="min-w-0">
            <span className="mb-0.5 block text-[10px] font-bold uppercase tracking-[0.18em] text-purple-300">
              Posted it?
            </span>
            <span className="block text-sm font-bold text-white">
              {platform === "tiktok"
                ? "Did you post this? Track real stats"
                : "Did you post this Reel? Track real likes"}
            </span>
            <span className="mt-0.5 block text-[11px] leading-relaxed text-zinc-400">
              Connect the post, start tracking results, and earn +1 analysis
            </span>
          </span>
        </span>
        <span className="relative z-10 grid h-8 w-8 flex-shrink-0 place-items-center rounded-full bg-purple-500 text-white shadow-lg shadow-purple-950/40 transition-transform group-hover:translate-x-1">
          <ArrowUpRight className="h-4 w-4" />
        </span>
      </button>
    </div>
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

      {(a.platform === "tiktok" || a.platform === "instagram") && (
        <PostLinkRow a={a} platform={a.platform} onUpdated={onUpdated} />
      )}

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
            Your{" "}
            <span className={cfg.textGradient}>
              {platform === "tiktok" ? "TikTok Projects" : "Instagram Reels"}
            </span>
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
