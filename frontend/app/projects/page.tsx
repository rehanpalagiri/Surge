"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { getMyAnalyses, deleteAnalysis, linkTikTokVideo, apiErrorDetail, AnalysisSummary } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { ProjectsSkeleton } from "@/components/Skeleton";
import { verdictDisplay } from "@/lib/verdicts";
import PlatformTabs from "@/components/PlatformTabs";
import { ArrowUpRight, CalendarDays, Link2, RefreshCw, Trash2, Video } from "lucide-react";
import { createPortal } from "react-dom";

function seededRand(seed: number): number {
  const x = Math.sin(seed + 1) * 10000;
  return x - Math.floor(x);
}

const _COLORS8 = ["#2DD4BF", "#fbbf24", "#ec4899", "#34d399", "#60a5fa", "#fb923c", "#f43f5e", "#10b981"];

const MEGA_CONFETTI = Array.from({ length: 80 }, (_, i) => {
  const angle = (i / 80) * 2 * Math.PI + seededRand(i * 3) * 0.5;
  const dist = 160 + seededRand(i * 7) * 380;
  return {
    color: _COLORS8[i % 8],
    tx: Math.round(Math.cos(angle) * dist),
    ty: Math.round(Math.sin(angle) * dist - 80),
    r: Math.round(seededRand(i * 13) * 720),
    size: 8 + Math.round(seededRand(i * 5) * 8),
    round: i % 3 === 0,
    delay: Math.round(seededRand(i * 11) * 400),
  };
});

const _COLORS6 = ["#2DD4BF", "#fbbf24", "#ec4899", "#34d399", "#60a5fa", "#fb923c"];

const MINI_BURST = Array.from({ length: 14 }, (_, i) => {
  const angle = (i / 14) * 2 * Math.PI + seededRand(i * 5) * 0.5;
  const dist = 30 + seededRand(i * 9) * 60;
  return {
    color: _COLORS6[i % 6],
    tx: Math.round(Math.cos(angle) * dist),
    ty: Math.round(Math.sin(angle) * dist),
    r: Math.round(seededRand(i * 7) * 360),
    size: 4 + Math.round(seededRand(i * 3) * 4),
    round: i % 2 === 0,
    delay: Math.round(seededRand(i * 13) * 80),
  };
});

const MEGA_FLOAT_EMOJI = [
  { emoji: "🎉", fx: -180, delay:  80, cls: "text-5xl" },
  { emoji: "🚀", fx:  -45, delay:   0, cls: "text-6xl" },
  { emoji: "⭐", fx:   50, delay: 160, cls: "text-4xl" },
  { emoji: "🎊", fx:  175, delay: 260, cls: "text-5xl" },
  { emoji: "🔥", fx:  -95, delay: 360, cls: "text-3xl" },
  { emoji: "✨", fx:  115, delay: 430, cls: "text-4xl" },
  { emoji: "🧡", fx: -145, delay: 210, cls: "text-4xl" },
  { emoji: "🌟", fx:  205, delay: 110, cls: "text-5xl" },
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showHowTo, setShowHowTo] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const [bursting, setBursting] = useState(false);
  const [burstOrigin, setBurstOrigin] = useState({ x: 0, y: 0 });
  const howTo = platform === "tiktok" ? TIKTOK_HOW_TO : INSTAGRAM_HOW_TO;

  // Glow the whole project card during celebration
  useEffect(() => {
    if (phase !== "celebrate") return;
    const card = containerRef.current?.closest("article") as HTMLElement | null;
    if (!card) return;
    card.style.borderColor = "rgb(45 212 191 / 0.75)";
    card.style.boxShadow = "0 0 0 1px rgb(45 212 191 / 0.35), 0 0 50px rgb(45 212 191 / 0.22)";
    card.style.transition = "border-color 0.25s, box-shadow 0.25s";
    return () => {
      card.style.borderColor = "";
      card.style.boxShadow = "";
    };
  }, [phase]);

  function handlePostedClick() {
    if (btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      setBurstOrigin({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
    }
    setBursting(true);
    setTimeout(() => {
      setBursting(false);
      setPhase("linking");
    }, 480);
  }

  async function fetchStats(url?: string) {
    setBusy(true);
    setError("");
    try {
      const updated = await linkTikTokVideo(a.id, url, undefined);
      onUpdated(a.id, {
        actual_views: updated.actual_views,
        actual_likes: updated.actual_likes,
        video_url: updated.video_url,
        counts_fetched_at: updated.counts_fetched_at,
      });
      setLink("");
      const pendingWarning =
        updated.video_url && !updated.counts_fetched_at
          ? "Link saved — stats couldn't be fetched right now. Try the refresh button in a few hours."
          : "";
      setPhase("celebrate");
      setTimeout(() => {
        setPhase("idle");
        if (pendingWarning) setError(pendingWarning);
      }, 3000);
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Couldn't fetch stats — try again."));
    } finally {
      setBusy(false);
    }
  }

  // Already linked — TikTok refreshes in-place; Instagram re-opens form
  if (a.video_url && phase === "idle") {
    const statsNotYetFetched = !a.counts_fetched_at && !!a.video_url;
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
          className="text-xs font-medium text-text-muted hover:text-text-primary border border-border hover:border-accent/50 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
        >
          {busy && <span className="pending-spinner mr-1.5 align-[-0.1em]" aria-hidden="true" />}
          {busy
            ? "Refreshing…"
            : platform === "tiktok"
            ? "↻ Capture current TikTok stats"
            : "↻ Capture current Instagram likes"}
        </button>
        {statsNotYetFetched && !error && (
          <p className="text-[11px] text-warning">
            Stats pending — our provider is temporarily down. Try refreshing in a few hours.
          </p>
        )}
        {platform === "instagram" && (
          <p className="text-[11px] text-text-muted">
            Instagram likes are recorded as observations; Surge does not infer reach from them.
          </p>
        )}
        {error && <p className={`text-xs ${error.includes("saved") ? "text-warning" : "text-danger"}`}>{error}</p>}
      </div>
    );
  }

  // Celebration burst — full-screen portal
  if (phase === "celebrate") {
    return (
      <>
        <div ref={containerRef} className="px-5 pb-4 h-8" />
        {createPortal(
          <div
            className="fixed inset-0 z-[9999] flex flex-col items-center justify-center overflow-hidden"
            style={{ animation: "celebrate-portal-exit 0.5s 2.5s ease-in forwards" }}
          >
            {/* Screen flash */}
            <div
              className="pointer-events-none absolute inset-0"
              style={{
                background: "radial-gradient(ellipse 80% 60% at 50% 40%, rgb(45 212 191 / 0.95), rgb(224 96 76 / 0.6) 45%, transparent 72%)",
                animation: "screen-flash 0.7s ease-out forwards",
              }}
            />

            {/* Dark backdrop */}
            <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" style={{ zIndex: -1 }} />

            {/* Mega confetti */}
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              {MEGA_CONFETTI.map((p, i) => (
                <span
                  key={i}
                  className="absolute"
                  style={{
                    width: p.size, height: p.size,
                    borderRadius: p.round ? "50%" : "3px",
                    backgroundColor: p.color,
                    "--tx": `${p.tx}px`,
                    "--ty": `${p.ty}px`,
                    "--r": `${p.r}deg`,
                    animation: `confetti-particle 1.6s ${p.delay}ms cubic-bezier(0.15, 0.8, 0.35, 1) forwards`,
                  } as React.CSSProperties}
                />
              ))}
            </div>

            {/* Shockwave rings */}
            {[0, 160, 320, 520].map((delay, i) => (
              <span
                key={i}
                className="pointer-events-none absolute rounded-full border-2 border-accent/50"
                style={{
                  width: 48, height: 48,
                  top: "50%", left: "50%",
                  animation: `pulse-ring 1.1s ${delay}ms ease-out forwards`,
                }}
              />
            ))}

            {/* Floating emoji */}
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              {MEGA_FLOAT_EMOJI.map((e, i) => (
                <span
                  key={i}
                  className={`absolute select-none ${e.cls}`}
                  style={{
                    "--fx": `${e.fx}px`,
                    animation: `mega-float-up 2.4s ${e.delay}ms ease-out forwards`,
                  } as React.CSSProperties}
                >
                  {e.emoji}
                </span>
              ))}
            </div>

            {/* Text */}
            <div className="relative z-10 flex flex-col items-center gap-4 px-6 text-center">
              <p
                className="text-5xl sm:text-7xl font-black tracking-[0.1em] text-white uppercase leading-tight"
                style={{ animation: "big-slam-in 0.7s 120ms cubic-bezier(0.2, 0.8, 0.2, 1) both" }}
              >
                You<br />posted it!
              </p>
              <p
                className="text-base sm:text-lg text-white/80 max-w-xs leading-relaxed"
                style={{ animation: "celebrate-text-in 0.5s 480ms cubic-bezier(0.2, 0.8, 0.2, 1) both" }}
              >
                Your video is live. Let&apos;s see how the world responds.
              </p>
              <div
                className="inline-flex items-center gap-2 rounded-full border border-yellow-400/40 bg-yellow-500/15 px-5 py-2 text-sm font-bold text-yellow-300"
                style={{
                  animation: "achievement-rise 0.5s 780ms cubic-bezier(0.2, 0.8, 0.2, 1) both",
                  boxShadow: "0 0 30px rgb(234 179 8 / 0.35)",
                }}
              >
                <span>🏆</span>
                <span>+1 analysis credit earned</span>
              </div>
            </div>
          </div>,
          document.body
        )}
      </>
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
          <input
            type="url"
            autoFocus
            placeholder={placeholder}
            value={link}
            onChange={(e) => setLink(e.target.value)}
            className="flex-1 min-w-0 bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
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
          className="text-[11px] text-text-muted hover:text-text-primary transition-colors hover:underline underline-offset-2"
        >
          {showHowTo
            ? "Hide tutorial ↑"
            : `Don't know how to find the ${platform === "tiktok" ? "TikTok" : "Instagram"} link? ↓`}
        </button>
        {showHowTo && (
          <ol className="space-y-2 pt-0.5 motion-pop">
            {howTo.map((step, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <span className="flex-shrink-0 h-5 w-5 grid place-items-center rounded-full bg-accent/15 text-accent text-[10px] font-bold">
                  {i + 1}
                </span>
                <p className="text-[11px] text-text-muted leading-relaxed pt-0.5">{step}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    );
  }

  // Idle, not yet linked
  return (
    <div className="px-5 pb-4 relative">
      {bursting && createPortal(
        <div className="fixed inset-0 pointer-events-none z-[9998]">
          <span
            className="absolute rounded-full border-[1.5px] border-accent/80"
            style={{
              width: 10, height: 10,
              left: burstOrigin.x, top: burstOrigin.y,
              animation: "posted-btn-ring 0.52s ease-out forwards",
            }}
          />
          {MINI_BURST.map((p, i) => (
            <span
              key={i}
              className="absolute"
              style={{
                width: p.size, height: p.size,
                borderRadius: p.round ? "50%" : "2px",
                backgroundColor: p.color,
                left: burstOrigin.x,
                top: burstOrigin.y,
                "--tx": `${p.tx}px`,
                "--ty": `${p.ty}px`,
                "--r": `${p.r}deg`,
                animation: `mini-burst 0.55s ${p.delay}ms ease-out forwards`,
              } as React.CSSProperties}
            />
          ))}
        </div>,
        document.body
      )}
      <div style={bursting ? { animation: "posted-btn-scale 0.45s ease-out" } : undefined}>
        <button
          ref={btnRef}
          type="button"
          onClick={handlePostedClick}
          disabled={bursting}
          className="project-link-cta group w-full text-left"
        >
          <span className="relative z-10 flex min-w-0 items-center gap-3">
            <span className="grid h-11 w-11 flex-shrink-0 place-items-center rounded-xl border border-accent/25 bg-accent/10 text-accent transition-transform group-hover:-translate-y-0.5 group-hover:scale-105">
              <Link2 className="h-5 w-5" strokeWidth={1.8} />
            </span>
            <span className="min-w-0">
              <span className="mb-0.5 block text-[10px] font-bold uppercase tracking-[0.18em] text-accent">
                Posted it?
              </span>
              <span className="block text-sm font-bold text-text-primary">
                {platform === "tiktok"
                  ? "Did you post this? Track real stats"
                  : "Did you post this Reel? Track real likes"}
              </span>
              <span className="mt-0.5 block text-[11px] leading-relaxed text-text-muted">
                Connect the post, start tracking results, and earn +1 analysis
              </span>
            </span>
          </span>
          <span className="relative z-10 grid h-8 w-8 flex-shrink-0 place-items-center rounded-full bg-accent text-background shadow-md transition-transform group-hover:translate-x-1">
            <ArrowUpRight className="h-4 w-4" />
          </span>
        </button>
      </div>
    </div>
  );
}

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
            <span className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-xl border border-border bg-surface text-accent">
              <Video className="h-5 w-5" strokeWidth={1.6} />
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-base font-bold text-text-primary">{projectName}</h2>
              <p className="mt-0.5 truncate text-xs capitalize text-text-muted">{a.niche || "General"}</p>
            </div>
          </div>
          {needsLink && (
            <span className="rounded-full border border-accent/25 bg-accent/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-accent">
              Needs link
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
          href={updateUrl}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted hover:border-accent/50 hover:text-text-primary"
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
