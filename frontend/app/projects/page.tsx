"use client";

import { useEffect, useRef, useState } from "react";
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

const CONFETTI_PARTICLES: Array<{ color: string; tx: number; ty: number; r: number; size: number; round: boolean; delay: number }> = [
  // First burst — centre cluster going up
  { color: "#a855f7", tx:   0, ty: -140, r: 270, size: 10, round: false, delay:   0 },
  { color: "#fbbf24", tx: -25, ty: -120, r:  45, size:  7, round: true,  delay:  30 },
  { color: "#ec4899", tx:  25, ty: -120, r: 180, size:  8, round: false, delay:  60 },
  { color: "#34d399", tx: -10, ty: -100, r: 315, size:  6, round: false, delay:  20 },
  { color: "#60a5fa", tx:  10, ty: -100, r:  90, size:  9, round: true,  delay:  50 },
  // Left spread
  { color: "#fb923c", tx: -60, ty: -130, r: 200, size:  7, round: false, delay:  40 },
  { color: "#a855f7", tx: -80, ty:  -90, r: 140, size: 10, round: true,  delay:  80 },
  { color: "#ec4899", tx:-110, ty: -110, r:  30, size:  6, round: false, delay: 100 },
  { color: "#fbbf24", tx: -45, ty:  -70, r: 255, size:  8, round: false, delay:  70 },
  { color: "#34d399", tx:-120, ty:  -50, r: 320, size:  7, round: true,  delay: 120 },
  // Right spread
  { color: "#60a5fa", tx:  60, ty: -130, r:  60, size:  9, round: false, delay:  40 },
  { color: "#fb923c", tx:  80, ty:  -90, r: 220, size:  6, round: true,  delay:  80 },
  { color: "#a855f7", tx: 110, ty: -110, r: 350, size: 10, round: false, delay: 100 },
  { color: "#ec4899", tx:  45, ty:  -70, r: 110, size:  7, round: false, delay:  70 },
  { color: "#fbbf24", tx: 120, ty:  -50, r: 170, size:  8, round: true,  delay: 120 },
  // Second wave — delayed
  { color: "#34d399", tx: -90, ty: -160, r:  80, size:  6, round: false, delay: 150 },
  { color: "#60a5fa", tx:  90, ty: -160, r: 300, size:  7, round: false, delay: 150 },
  { color: "#fb923c", tx: -50, ty: -150, r: 195, size: 10, round: true,  delay: 180 },
  { color: "#a855f7", tx:  50, ty: -150, r:  25, size:  8, round: false, delay: 180 },
  { color: "#ec4899", tx:-100, ty:  -80, r: 145, size:  6, round: false, delay: 200 },
  { color: "#fbbf24", tx: 100, ty:  -80, r: 265, size:  9, round: true,  delay: 200 },
  // Falling outward — drift sideways / slightly down for realism
  { color: "#34d399", tx:-125, ty:  30, r:  50, size:  7, round: false, delay:  60 },
  { color: "#60a5fa", tx: 125, ty:  30, r: 230, size:  6, round: false, delay:  60 },
  { color: "#a855f7", tx:-110, ty:  60, r: 100, size:  8, round: true,  delay:  90 },
  { color: "#fb923c", tx: 110, ty:  60, r: 280, size:  9, round: false, delay:  90 },
  { color: "#ec4899", tx: -65, ty:  80, r: 170, size:  6, round: false, delay: 110 },
  { color: "#fbbf24", tx:  65, ty:  80, r:  10, size:  7, round: true,  delay: 110 },
  { color: "#34d399", tx:   0, ty:  90, r: 310, size: 10, round: false, delay: 140 },
];

const FLOAT_EMOJI = [
  { emoji: "🎉", fx: -90, delay:  60, cls: "text-2xl" },
  { emoji: "🚀", fx: -30, delay:   0, cls: "text-3xl" },
  { emoji: "⭐", fx:  20, delay: 130, cls: "text-xl"  },
  { emoji: "🎊", fx:  75, delay: 220, cls: "text-2xl" },
  { emoji: "🔥", fx: -55, delay: 310, cls: "text-lg"  },
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
  const containerRef = useRef<HTMLDivElement>(null);
  const howTo = platform === "tiktok" ? TIKTOK_HOW_TO : INSTAGRAM_HOW_TO;

  // Glow the whole project card during celebration
  useEffect(() => {
    if (phase !== "celebrate") return;
    const card = containerRef.current?.closest("article") as HTMLElement | null;
    if (!card) return;
    card.style.borderColor = "rgb(168 85 247 / 0.75)";
    card.style.boxShadow = "0 0 0 1px rgb(168 85 247 / 0.35), 0 0 50px rgb(168 85 247 / 0.22)";
    card.style.transition = "border-color 0.25s, box-shadow 0.25s";
    return () => {
      card.style.borderColor = "";
      card.style.boxShadow = "";
    };
  }, [phase]);

  function handlePostedClick() {
    setPhase("celebrate");
    setTimeout(() => setPhase("linking"), 3000);
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
      <div ref={containerRef} className="relative overflow-hidden px-5 pb-6 pt-4 flex flex-col items-center gap-3 min-h-[190px]">
        {/* Radial purple glow bg */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{ background: "radial-gradient(ellipse 90% 70% at 50% 55%, rgb(168 85 247 / 0.22) 0%, transparent 68%)" }}
        />

        {/* Shockwave rings — burst from centre */}
        {[0, 180, 360].map((delay, i) => (
          <span
            key={i}
            className="pointer-events-none absolute rounded-full border-2 border-purple-400/60"
            style={{
              width: 36, height: 36,
              top: "50%", left: "50%",
              animation: `pulse-ring 0.95s ${delay}ms ease-out forwards`,
            }}
          />
        ))}

        {/* Confetti particles */}
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          {CONFETTI_PARTICLES.map((p, i) => (
            <span
              key={i}
              className="absolute"
              style={{
                width: p.size,
                height: p.size,
                borderRadius: p.round ? "50%" : "2px",
                backgroundColor: p.color,
                "--tx": `${p.tx}px`,
                "--ty": `${p.ty}px`,
                "--r": `${p.r}deg`,
                animation: `confetti-particle 1.3s ${p.delay}ms cubic-bezier(0.15, 0.8, 0.35, 1) forwards`,
              } as React.CSSProperties}
            />
          ))}
        </div>

        {/* Floating emoji */}
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          {FLOAT_EMOJI.map((e, i) => (
            <span
              key={i}
              className={`absolute select-none ${e.cls}`}
              style={{
                "--fx": `${e.fx}px`,
                animation: `float-up-fade 2s ${e.delay}ms ease-out forwards`,
              } as React.CSSProperties}
            >
              {e.emoji}
            </span>
          ))}
        </div>

        {/* Text content */}
        <div className="relative z-10 flex flex-col items-center gap-2 pt-6">
          <p
            className="text-2xl font-extrabold tracking-widest text-white uppercase"
            style={{ animation: "celebrate-text-in 0.55s 200ms cubic-bezier(0.2, 0.8, 0.2, 1) both" }}
          >
            You posted it!
          </p>
          <p
            className="text-sm text-zinc-400 text-center"
            style={{ animation: "celebrate-text-in 0.5s 360ms cubic-bezier(0.2, 0.8, 0.2, 1) both" }}
          >
            Your video is live. Let&apos;s see how the world responds.
          </p>
          <div
            className="mt-1.5 inline-flex items-center gap-1.5 rounded-full border border-yellow-400/40 bg-yellow-500/15 px-4 py-1.5 text-xs font-bold text-yellow-300"
            style={{
              animation: "achievement-rise 0.45s 620ms cubic-bezier(0.2, 0.8, 0.2, 1) both",
              boxShadow: "0 0 18px rgb(234 179 8 / 0.28)",
            }}
          >
            <span>🏆</span>
            <span>+1 analysis credit earned</span>
          </div>
        </div>
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
