"use client";

import { useState, useEffect, useCallback, Fragment } from "react";
import {
  getAdminSeeds,
  addSeedVideo,
  deleteSeedVideo,
  seedFromUrl,
  getFetchStatus,
  ackFetchStatus,
  getApiUsage,
  triggerHarvest,
  getHarvestStatus,
  generateInsights,
  getInsights,
  triggerTrendHarvest,
  getTrendHarvestStatus,
  generateTrends,
  getTrends,
  SeedVideoOut,
  FetchStatus,
  ApiUsage,
  HarvestStatus,
  NicheInsightRow,
  GenerateInsightsResult,
  TrendHarvestStatus,
  TrendRow,
  GenerateTrendsResult,
} from "@/lib/api";
import { AdminDataSkeleton, SkeletonButton, SkeletonCard, SkeletonInput, SkeletonTitle } from "@/components/Skeleton";
import BrandLogo from "@/components/BrandLogo";

// Must stay in sync with CANONICAL_NICHES in backend/services/niche_classifier.py —
// seed matching is an exact string compare against the classified user niche.
const NICHES = [
  "Fitness",
  "Comedy",
  "Food",
  "Fashion",
  "Beauty",
  "Education",
  "Gaming",
  "Music",
  "Dance",
  "Tech",
  "Finance",
  "Money",
  "Side Hustles",
  "Crypto",
  "Business",
  "Health",
  "Mental Health",
  "Yoga",
  "Travel",
  "Lifestyle",
  "Motivation",
  "Sports",
  "Dating",
  "Art",
  "Pets",
  "Parenting",
  "Kids",
  "Vegan",
  "DIY & Crafts",
  "Home Decor",
  "Cleaning",
  "Career",
  "Real Estate",
  "Outdoors",
  "True Crime",
  "Books",
  "Spirituality",
  "Movies & TV",
  "Anime",
  "Edits",
  "Cars",
  "Photography",
  "Sustainability",
  "College",
  "Luxury",
  "Thrifting",
  "Hair",
  "Looksmaxxing",
  "ASMR",
  "News",
];

type Tab = "url" | "manual";
type Platform = "tiktok" | "instagram";
type MainTab = "seeds" | "harvest" | "intelligence";

function parseSeedSummary(raw: string | null): string {
  if (!raw) return "";
  try {
    const d = JSON.parse(raw);
    return typeof d?.seed_summary === "string" ? d.seed_summary : "";
  } catch { return ""; }
}

function UsageBar({ used, limit, resetsAt }: { used: number; limit: number; resetsAt: string }) {
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const color =
    used >= limit ? "bg-danger" : used >= limit * 0.75 ? "bg-yellow-400" : "bg-success";
  const textColor =
    used >= limit ? "text-danger" : used >= limit * 0.75 ? "text-yellow-400" : "text-success";

  const resetDate = new Date(resetsAt).toLocaleDateString("en-US", {
    month: "short", day: "numeric",
  });

  return (
    <div className="bg-surface border border-border rounded-xl px-4 py-3 space-y-1.5">
      <div className="flex justify-between items-center text-xs">
        <span className="text-text-muted font-medium">Instagram API calls this month</span>
        <span className={`font-bold ${textColor}`}>{used} / {limit}</span>
      </div>
      <div className="w-full h-1.5 bg-border rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-text-muted/60 text-[11px]">
        {used >= limit
          ? "Limit reached — use Manual Upload below."
          : `Resets ${resetDate}`}
      </p>
    </div>
  );
}

export default function AdminPage() {
  const [password, setPassword] = useState("");
  const [authChecked, setAuthChecked] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authPending, setAuthPending] = useState(false);
  const [seeds, setSeeds] = useState<SeedVideoOut[]>([]);
  const [seedsLoaded, setSeedsLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [tab, setTab] = useState<Tab>("url");
  const [activePlatform, setActivePlatform] = useState<Platform>("tiktok");
  const [mainTab, setMainTab] = useState<MainTab>("seeds");

  // URL fetch state
  const [fetchUrl, setFetchUrl] = useState("");
  const [fetchNiche, setFetchNiche] = useState("Fitness");
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState("");
  const [fetchStatus, setFetchStatus] = useState<FetchStatus | null>(null);
  const [apiUsage, setApiUsage] = useState<ApiUsage | null>(null);

  // Harvest state
  const [harvestStatus, setHarvestStatus] = useState<HarvestStatus | null>(null);
  const [harvesting, setHarvesting] = useState(false);
  const [harvestError, setHarvestError] = useState("");
  const [harvestMinViews, setHarvestMinViews] = useState("500000");
  const [harvestMaxViews, setHarvestMaxViews] = useState("");
  const [harvestMinLikes, setHarvestMinLikes] = useState("1000");
  const [harvestMaxPer, setHarvestMaxPer] = useState("3");
  const [harvestPlatform, setHarvestPlatform] = useState<"tiktok" | "instagram">("tiktok");
  const [harvestNiches, setHarvestNiches] = useState<string[]>([]);
  const [harvestDetailExpanded, setHarvestDetailExpanded] = useState<Record<string, boolean>>({});

  // Niche Intelligence state
  const [insights, setInsights] = useState<NicheInsightRow[]>([]);
  const [generatingInsights, setGeneratingInsights] = useState(false);
  const [insightError, setInsightError] = useState("");
  const [insightResult, setInsightResult] = useState<GenerateInsightsResult | null>(null);
  const [insightNiche, setInsightNiche] = useState("");

  // Trend Intelligence state
  const [trendHarvestStatus, setTrendHarvestStatus] = useState<TrendHarvestStatus | null>(null);
  const [trendHarvesting, setTrendHarvesting] = useState(false);
  const [trendHarvestError, setTrendHarvestError] = useState("");
  const [trendMinVelocity, setTrendMinVelocity] = useState("20000");
  const [trendMaxAge, setTrendMaxAge] = useState("30");
  const [trends, setTrends] = useState<TrendRow[]>([]);
  const [generatingTrends, setGeneratingTrends] = useState(false);
  const [trendError, setTrendError] = useState("");
  const [trendResult, setTrendResult] = useState<GenerateTrendsResult | null>(null);
  const [trendNiche, setTrendNiche] = useState("");

  // Manual upload state
  const [file, setFile] = useState<File | null>(null);
  const [niche, setNiche] = useState("Fitness");
  const [viewCount, setViewCount] = useState("");
  const [likeCount, setLikeCount] = useState("");
  const [notes, setNotes] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const igUsed = apiUsage?.instagram.used ?? 0;
  const igLimit = apiUsage?.instagram.limit ?? 20;
  const igResetsAt = apiUsage?.instagram.resets_at ?? "";
  const igAtLimit = igUsed >= igLimit;

  const refreshFetchStatus = useCallback(async (pw: string) => {
    try { setFetchStatus(await getFetchStatus(pw)); } catch { /* non-fatal */ }
  }, []);

  const refreshApiUsage = useCallback(async (pw: string) => {
    try { setApiUsage(await getApiUsage(pw)); } catch { /* non-fatal */ }
  }, []);

  const refreshHarvestStatus = useCallback(async (pw: string) => {
    try { setHarvestStatus(await getHarvestStatus(pw)); } catch { /* non-fatal */ }
  }, []);

  const loadSeeds = useCallback(async (pw: string) => {
    try {
      setSeeds(await getAdminSeeds(pw));
      setLoadError("");
    } catch (err: unknown) {
      setLoadError(err instanceof Error ? err.message : "Failed to load seeds");
    } finally {
      setSeedsLoaded(true);
    }
  }, []);

  const loadInsights = useCallback(async (pw: string, platform: string) => {
    try { setInsights(await getInsights(pw, platform)); } catch { /* non-fatal */ }
  }, []);

  const loadTrends = useCallback(async (pw: string, platform: string) => {
    try { setTrends(await getTrends(pw, platform)); } catch { /* non-fatal */ }
  }, []);

  const refreshTrendHarvestStatus = useCallback(async (pw: string) => {
    try { setTrendHarvestStatus(await getTrendHarvestStatus(pw)); } catch { /* non-fatal */ }
  }, []);

  useEffect(() => {
    // An older build persisted the admin password in localStorage — purge the
    // stale plaintext credential wherever it still lingers.
    try { localStorage.removeItem("viraliq_admin_pw"); } catch { /* ignore */ }
    const saved = sessionStorage.getItem("viraliq_admin_pw");
    if (saved) {
      setPassword(saved);
      setAuthed(true);
      loadSeeds(saved);
      refreshFetchStatus(saved);
      refreshApiUsage(saved);
      refreshHarvestStatus(saved);
      loadInsights(saved, "tiktok");
      loadTrends(saved, "tiktok");
      refreshTrendHarvestStatus(saved);
    }
    setAuthChecked(true);
  }, [loadSeeds, refreshFetchStatus, refreshApiUsage, refreshHarvestStatus, loadInsights, loadTrends, refreshTrendHarvestStatus]);

  // Reload insights/trends when platform changes
  useEffect(() => {
    setViewCount("");
    if (authed) {
      loadInsights(password, activePlatform);
      loadTrends(password, activePlatform);
    }
  }, [activePlatform]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleAuth(e: React.FormEvent) {
    e.preventDefault();
    if (authPending) return;
    setAuthPending(true);
    try {
      await getAdminSeeds(password);
      sessionStorage.setItem("viraliq_admin_pw", password);
      setAuthed(true);
      setAuthError("");
      loadSeeds(password);
      refreshFetchStatus(password);
      refreshApiUsage(password);
      refreshHarvestStatus(password);
      loadInsights(password, activePlatform);
      loadTrends(password, activePlatform);
      refreshTrendHarvestStatus(password);
    } catch { setAuthError("Invalid password."); }
    finally { setAuthPending(false); }
  }

  async function handleFetchFromUrl(e: React.FormEvent) {
    e.preventDefault();
    if (!fetchUrl.trim()) return;
    setFetching(true);
    setFetchError("");
    try {
      await seedFromUrl(fetchUrl.trim(), fetchNiche, password);
      setFetchUrl("");
      await Promise.all([loadSeeds(password), refreshFetchStatus(password), refreshApiUsage(password)]);
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Fetch failed");
      await refreshFetchStatus(password);
    } finally {
      setFetching(false);
    }
  }

  async function dismissFetchWarning() {
    setFetchStatus({ broken: false });
    try { await ackFetchStatus(password); } catch { /* ignore */ }
  }

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("platform", activePlatform);
      form.append("niche", niche);
      if (activePlatform === "tiktok") form.append("view_count", viewCount);
      form.append("like_count", likeCount);
      if (notes) form.append("notes", notes);
      await addSeedVideo(form, password);
      setFile(null);
      setViewCount("");
      setLikeCount("");
      setNotes("");
      loadSeeds(password);
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("Delete this seed video?")) return;
    try {
      await deleteSeedVideo(id, password);
      setSeeds((prev) => prev.filter((s) => s.id !== id));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function handleHarvest() {
    setHarvesting(true);
    setHarvestError("");
    try {
      await triggerHarvest(password, {
        platform: harvestPlatform,
        min_views: parseInt(harvestMinViews) || 500_000,
        ...(harvestMaxViews.trim() ? { max_views: parseInt(harvestMaxViews) } : {}),
        min_likes: parseInt(harvestMinLikes) || 1_000,
        max_per_niche: parseInt(harvestMaxPer) || 3,
        ...(harvestNiches.length > 0 ? { niches: harvestNiches } : {}),
      });
      const poll = async () => {
        try {
          const s = await getHarvestStatus(password);
          setHarvestStatus(s);
          const platformStatus = harvestPlatform === "instagram" ? s.instagram : s.tiktok;
          if (platformStatus?.status === "running") {
            setTimeout(poll, 8000);
          } else {
            setHarvesting(false);
            loadSeeds(password);
          }
        } catch {
          setHarvesting(false);
        }
      };
      setTimeout(poll, 5000);
    } catch (err: unknown) {
      setHarvestError(err instanceof Error ? err.message : "Harvest failed");
      setHarvesting(false);
    }
  }

  async function handleGenerateInsights() {
    setGeneratingInsights(true);
    setInsightError("");
    setInsightResult(null);
    try {
      const result = await generateInsights(password, activePlatform, insightNiche || undefined);
      setInsightResult(result);
      await loadInsights(password, activePlatform);
    } catch (err: unknown) {
      setInsightError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGeneratingInsights(false);
    }
  }

  async function handleTrendHarvest() {
    setTrendHarvesting(true);
    setTrendHarvestError("");
    try {
      await triggerTrendHarvest(password, {
        max_age_days: parseInt(trendMaxAge) || 30,
        min_velocity: parseInt(trendMinVelocity) || 20_000,
        max_per_niche: 2,
      });
      const poll = async () => {
        try {
          const s = await getTrendHarvestStatus(password);
          setTrendHarvestStatus(s);
          if (s.status === "running") {
            setTimeout(poll, 8000);
          } else {
            setTrendHarvesting(false);
            loadSeeds(password);
            loadTrends(password, activePlatform);
          }
        } catch {
          setTrendHarvesting(false);
        }
      };
      setTimeout(poll, 5000);
    } catch (err: unknown) {
      setTrendHarvestError(err instanceof Error ? err.message : "Trend harvest failed");
      setTrendHarvesting(false);
    }
  }

  async function handleGenerateTrends() {
    setGeneratingTrends(true);
    setTrendError("");
    setTrendResult(null);
    try {
      const result = await generateTrends(password, activePlatform, trendNiche || undefined);
      setTrendResult(result);
      await loadTrends(password, activePlatform);
    } catch (err: unknown) {
      setTrendError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGeneratingTrends(false);
    }
  }

  function handleLogout() {
    sessionStorage.removeItem("viraliq_admin_pw");
    setAuthed(false);
    setPassword("");
    setSeeds([]);
    setSeedsLoaded(false);
  }

  if (!authChecked) {
    return (
      <main className="min-h-screen flex items-center justify-center px-4 bg-background">
        <SkeletonCard className="w-full max-w-sm space-y-5">
          <SkeletonTitle width="42%" className="mx-auto" />
          <SkeletonInput />
          <SkeletonButton className="w-full" />
        </SkeletonCard>
      </main>
    );
  }

  if (!authed) {
    return (
      <main className="min-h-screen flex items-center justify-center px-4 bg-background">
        <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-8 space-y-6">
          <div className="text-center">
            <div className="text-4xl mb-3">🔐</div>
            <h1 className="text-xl font-bold text-text-primary">Admin Panel</h1>
            <p className="text-text-muted text-sm mt-1">Enter your admin password</p>
          </div>
          <form onSubmit={handleAuth} className="space-y-4">
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
            {authError && <p className="text-danger text-sm">{authError}</p>}
            <button type="submit" disabled={authPending} aria-busy={authPending} className="w-full gradient-btn text-white font-semibold py-3 rounded-xl disabled:opacity-50">
              {authPending && <span className="pending-spinner mr-2 align-[-0.1em]" aria-hidden="true" />}
              {authPending ? "Signing in…" : "Sign In"}
            </button>
          </form>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      {/* ── Top nav ── */}
      <nav className="border-b border-border bg-surface/50 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-0 flex items-stretch justify-between">
          {/* Left: brand + main tabs */}
          <div className="flex items-stretch gap-1">
            <span className="flex items-center gap-1.5 pr-6"><BrandLogo href={null} /><span className="font-bold text-text-primary">Admin</span></span>
            {(["seeds", "harvest", "intelligence"] as MainTab[]).map((t) => (
              <button
                key={t}
                onClick={() => setMainTab(t)}
                className={`px-5 py-4 text-sm font-semibold capitalize transition-colors border-b-2 ${
                  mainTab === t
                    ? "text-text-primary border-accent"
                    : "text-text-muted border-transparent hover:text-text-primary"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Right: platform toggle (Seeds + Intelligence) + sign out */}
          <div className="flex items-center gap-3">
            {mainTab !== "harvest" && (
              <div className="flex gap-1">
                {(["tiktok", "instagram"] as Platform[]).map((p) => (
                  <button
                    key={p}
                    onClick={() => setActivePlatform(p)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      activePlatform === p
                        ? "bg-accent/15 border border-accent/40 text-text-primary"
                        : "text-text-muted hover:text-text-primary"
                    }`}
                  >
                    {p === "tiktok" ? "TikTok" : "Instagram"}
                  </button>
                ))}
              </div>
            )}
            <button onClick={handleLogout} className="text-text-muted text-sm hover:text-danger transition-colors py-4">
              Sign out
            </button>
          </div>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">

        {/* API failure banner — always visible regardless of tab */}
        {fetchStatus?.broken && (
          <div className="bg-danger/10 border border-danger/40 rounded-2xl p-4 flex items-start justify-between gap-4">
            <div className="text-sm text-text-primary">
              <p className="font-semibold text-danger mb-1">⚠️ Auto-fetch last failed</p>
              <p className="text-text-muted">
                {fetchStatus.when ? new Date(fetchStatus.when).toLocaleString() : ""}
                {fetchStatus.message ? `: ${fetchStatus.message}` : ""}
              </p>
              <p className="text-text-muted mt-1">Use Manual Upload in the Seeds tab, or retry the URL.</p>
            </div>
            <button onClick={dismissFetchWarning} className="flex-shrink-0 text-text-muted hover:text-text-primary text-sm">
              Dismiss
            </button>
          </div>
        )}

        {/* ══════════════════════════════════════════════════
            SEEDS TAB
        ══════════════════════════════════════════════════ */}
        {mainTab === "seeds" && (
          <div className="space-y-6">

            {/* Add seed card */}
            <div className="bg-card border border-border rounded-2xl overflow-hidden">
              <div className="flex border-b border-border">
                {(["url", "manual"] as Tab[]).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`flex-1 py-3 text-sm font-medium transition-colors ${
                      tab === t
                        ? "text-text-primary border-b-2 border-accent bg-card"
                        : "text-text-muted hover:text-text-primary bg-surface/40"
                    }`}
                  >
                    {t === "url" ? "Add from URL" : "Manual Upload"}
                  </button>
                ))}
              </div>

              <div className="p-6">
                {/* ── URL tab ── */}
                {tab === "url" && (
                  <div className="space-y-4">
                    <p className="text-text-muted text-sm">
                      {activePlatform === "tiktok"
                        ? "Paste a TikTok video URL — fetched via tikwm.com, unlimited."
                        : "Paste an Instagram Reel URL — fetched via EaseApi (20/month free). Likes only; views are hidden by Instagram."}
                    </p>

                    {activePlatform === "instagram" && apiUsage && (
                      <UsageBar used={igUsed} limit={igLimit} resetsAt={igResetsAt} />
                    )}

                    {activePlatform === "instagram" && igAtLimit && (
                      <div className="bg-warning/10 border border-warning/30 rounded-xl px-4 py-3 text-sm text-warning">
                        Monthly limit reached — switch to{" "}
                        <button onClick={() => setTab("manual")} className="underline font-medium">
                          Manual Upload
                        </button>.
                      </div>
                    )}

                    <form onSubmit={handleFetchFromUrl} className="space-y-3">
                      <div>
                        <label className="block text-sm text-text-muted mb-1">URL</label>
                        <input
                          type="url"
                          placeholder={
                            activePlatform === "tiktok"
                              ? "https://www.tiktok.com/@user/video/..."
                              : "https://www.instagram.com/reel/..."
                          }
                          value={fetchUrl}
                          onChange={(e) => setFetchUrl(e.target.value)}
                          required
                          className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
                        />
                      </div>
                      <div>
                        <label className="block text-sm text-text-muted mb-1">Niche</label>
                        <select
                          value={fetchNiche}
                          onChange={(e) => setFetchNiche(e.target.value)}
                          className="w-full md:w-48 bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary focus:outline-none focus:border-accent"
                        >
                          {NICHES.map((n) => <option key={n} value={n} className="bg-card">{n}</option>)}
                        </select>
                      </div>
                      {fetchError && <p className="text-danger text-sm">{fetchError}</p>}
                      <button
                        type="submit"
                        disabled={fetching || (activePlatform === "instagram" && igAtLimit)}
                        className="gradient-btn text-white font-semibold px-6 py-2.5 rounded-xl disabled:opacity-50 whitespace-nowrap"
                      >
                        {fetching
                          ? activePlatform === "instagram"
                            ? "Fetching from Instagram…"
                            : "Fetching from TikTok…"
                          : "Fetch & Analyze"}
                      </button>
                    </form>
                  </div>
                )}

                {/* ── Manual upload tab ── */}
                {tab === "manual" && (
                  <div className="space-y-4">
                    <p className="text-text-muted text-sm">
                      Upload a saved video file directly. Use this when the URL fetch fails or as an
                      unlimited fallback.
                      {activePlatform === "instagram" && " Instagram hides view counts — only likes are used."}
                    </p>
                    <form onSubmit={handleUpload} className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm text-text-muted mb-1">Video file</label>
                          <input
                            type="file"
                            accept=".mp4,.mov"
                            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                            className="w-full text-text-muted text-sm file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-surface file:text-text-primary file:cursor-pointer"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-text-muted mb-1">Niche</label>
                          <select
                            value={niche}
                            onChange={(e) => setNiche(e.target.value)}
                            className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary focus:outline-none focus:border-accent"
                          >
                            {NICHES.map((n) => <option key={n} value={n} className="bg-card">{n}</option>)}
                          </select>
                        </div>

                        {activePlatform === "tiktok" && (
                          <div>
                            <label className="block text-sm text-text-muted mb-1">View count</label>
                            <input
                              type="number"
                              min="0"
                              placeholder="e.g. 2500000"
                              value={viewCount}
                              onChange={(e) => setViewCount(e.target.value)}
                              required
                              className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
                            />
                          </div>
                        )}

                        <div>
                          <label className="block text-sm text-text-muted mb-1">
                            Like count
                            {activePlatform === "instagram" && (
                              <span className="ml-1 text-text-muted/60 font-normal">(primary metric)</span>
                            )}
                          </label>
                          <input
                            type="number"
                            min="0"
                            placeholder="e.g. 334000"
                            value={likeCount}
                            onChange={(e) => setLikeCount(e.target.value)}
                            required
                            className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
                          />
                        </div>
                      </div>

                      <div className="bg-surface/60 border border-border rounded-xl px-4 py-3 text-xs text-text-muted">
                        Legacy seed tool: CraftLint creates an observable craft record and attaches
                        an internal outcome band. These records do not affect new live craft reviews. The video is deleted afterward. If
                        analysis fails, the seed is not saved — just retry.
                      </div>

                      <div>
                        <label className="block text-sm text-text-muted mb-1">Notes (optional)</label>
                        <textarea
                          placeholder="e.g. Strong hook, trending audio, mid-roll drop off..."
                          value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                          rows={2}
                          className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent resize-none"
                        />
                      </div>

                      {uploadError && <p className="text-danger text-sm">{uploadError}</p>}

                      <button
                        type="submit"
                        disabled={uploading}
                        className="gradient-btn text-white font-semibold px-6 py-2.5 rounded-xl disabled:opacity-50"
                      >
                        {uploading ? "Analyzing with Gemini… (~20–30s)" : "Add & Analyze Seed Video"}
                      </button>
                    </form>
                  </div>
                )}
              </div>
            </div>

            {/* Seed table */}
            <div className="bg-card border border-border rounded-2xl p-6">
              <div className="flex justify-between items-center mb-5">
                <h2 className="text-text-primary font-semibold text-lg">Seed Library</h2>
                <span className="text-text-muted text-sm bg-surface border border-border px-3 py-1 rounded-full">
                  {seeds.length} video{seeds.length !== 1 ? "s" : ""}
                </span>
              </div>

              {loadError && <p className="text-danger text-sm mb-4">{loadError}</p>}

              {!seedsLoaded ? (
                <AdminDataSkeleton />
              ) : seeds.length === 0 ? (
                <p className="text-text-muted text-sm text-center py-8">No seed videos yet. Add some above.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-text-muted border-b border-border">
                        <th className="text-left py-2 pr-4">Platform</th>
                        <th className="text-left py-2 pr-4">Niche</th>
                        <th className="text-right py-2 pr-4">Views</th>
                        <th className="text-right py-2 pr-4">Likes</th>
                        <th className="text-center py-2 pr-4">Legacy band</th>
                        <th className="text-left py-2 pr-4">Summary</th>
                        <th className="text-left py-2 pr-4">Date</th>
                        <th className="text-right py-2">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {seeds.map((seed) => {
                        const summary = parseSeedSummary(seed.gemini_analysis);
                        const isOpen = expandedId === seed.id;
                        const ratingColor =
                          seed.rating == null ? "text-text-muted bg-surface"
                          : seed.rating >= 6 ? "text-success bg-success/10"
                          : seed.rating <= 4 ? "text-danger bg-danger/10"
                          : "text-text-muted bg-surface";
                        return (
                          <Fragment key={seed.id}>
                            <tr className="border-b border-border/50 hover:bg-surface/50 transition-colors">
                              <td className="py-2.5 pr-4">
                                <div className="flex items-center gap-1.5">
                                  <span className="text-text-muted text-xs font-medium bg-surface border border-border px-2 py-0.5 rounded-full capitalize">
                                    {seed.platform}
                                  </span>
                                  {seed.source === "user" && (
                                    <span title="Auto-promoted from a verified user-posted video" className="text-[10px] font-semibold text-accent bg-accent/10 px-1.5 py-0.5 rounded-full">
                                      👤 user
                                    </span>
                                  )}
                                  {seed.source === "harvest" && (
                                    <span title="Auto-harvested via keyword search" className="text-[10px] font-semibold text-emerald-400 bg-emerald-400/10 px-1.5 py-0.5 rounded-full">
                                      🤖 auto
                                    </span>
                                  )}
                                  {seed.source === "trending" && (
                                    <span title="Harvested from trend feed — velocity-filtered recent video" className="text-[10px] font-semibold text-yellow-400 bg-yellow-400/10 px-1.5 py-0.5 rounded-full">
                                      📈 trend
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="py-2.5 pr-4 text-text-primary font-medium">{seed.niche}</td>
                              <td className="py-2.5 pr-4 text-right text-text-primary">
                                {seed.view_count != null ? seed.view_count.toLocaleString() : (
                                  <span className="text-text-muted/50 text-xs">—</span>
                                )}
                              </td>
                              <td className="py-2.5 pr-4 text-right text-text-muted">
                                {seed.like_count.toLocaleString()}
                              </td>
                              <td className="py-2.5 pr-4 text-center">
                                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${ratingColor}`}>
                                  {seed.rating == null ? "—" : `${seed.rating}/10`}
                                </span>
                              </td>
                              <td className="py-2.5 pr-4">
                                {summary ? (
                                  <button onClick={() => setExpandedId(isOpen ? null : seed.id)} className="text-accent hover:underline text-xs">
                                    {isOpen ? "Hide" : "View"}
                                  </button>
                                ) : (
                                  <span className="text-text-muted text-xs">—</span>
                                )}
                              </td>
                              <td className="py-2.5 pr-4 text-text-muted text-xs">
                                {new Date(seed.created_at).toLocaleDateString()}
                              </td>
                              <td className="py-2.5 text-right">
                                <button onClick={() => handleDelete(seed.id)} className="text-danger/60 hover:text-danger text-xs transition-colors">
                                  Delete
                                </button>
                              </td>
                            </tr>
                            {isOpen && summary && (
                              <tr className="border-b border-border/50">
                                <td colSpan={8} className="py-3 px-4 bg-surface/40">
                                  <p className="text-text-muted text-xs uppercase tracking-widest font-semibold mb-1">
                                    AI seed summary (read by the scoring model)
                                  </p>
                                  <p className="text-text-primary text-sm whitespace-pre-wrap">{summary}</p>
                                  {seed.notes && (
                                    <p className="text-text-muted text-xs mt-2">Notes: {seed.notes}</p>
                                  )}
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════
            HARVEST TAB
        ══════════════════════════════════════════════════ */}
        {mainTab === "harvest" && (
          <div className="space-y-6">

            {/* Auto-Harvest */}
            <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
              <div>
                <h2 className="text-text-primary font-semibold text-lg">Auto-Harvest Seeds</h2>
                <p className="text-text-muted text-sm mt-1">
                  TikTok: searches via tikwm (free, unlimited). Instagram: searches via HikerAPI (requires HIKERAPI_KEY, 100 free requests/month).
                </p>
              </div>

              <div className="flex gap-2">
                {(["tiktok", "instagram"] as const).map((p) => (
                  <button key={p} onClick={() => setHarvestPlatform(p)}
                    className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-colors ${
                      harvestPlatform === p
                        ? "gradient-btn text-white"
                        : "border border-border text-text-muted hover:text-text-primary"
                    }`}>
                    {p === "tiktok" ? "TikTok" : "Instagram"}
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap gap-4 items-end">
                {harvestPlatform === "tiktok" ? (
                  <>
                    <div>
                      <label className="block text-xs text-text-muted mb-1">Min views</label>
                      <input type="number" value={harvestMinViews}
                        onChange={(e) => setHarvestMinViews(e.target.value)}
                        className="w-36 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-accent" />
                    </div>
                    <div>
                      <label className="block text-xs text-text-muted mb-1">
                        Max views
                        <span className="ml-1 text-text-muted/50 font-normal">(blank = no cap)</span>
                      </label>
                      <input type="number" value={harvestMaxViews}
                        placeholder="e.g. 50000"
                        onChange={(e) => setHarvestMaxViews(e.target.value)}
                        className="w-36 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm placeholder-text-muted/40 focus:outline-none focus:border-accent" />
                    </div>
                  </>
                ) : (
                  <div>
                    <label className="block text-xs text-text-muted mb-1">Min likes</label>
                    <input type="number" value={harvestMinLikes}
                      onChange={(e) => setHarvestMinLikes(e.target.value)}
                      className="w-36 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-accent" />
                  </div>
                )}
                <div>
                  <label className="block text-xs text-text-muted mb-1">Max per niche</label>
                  <input type="number" min="1" max="10" value={harvestMaxPer}
                    onChange={(e) => setHarvestMaxPer(e.target.value)}
                    className="w-28 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-accent" />
                </div>
                <div className="w-full">
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs text-text-muted">
                      Target niches
                      <span className="ml-1.5 text-text-muted/50">
                        {harvestNiches.length === 0 ? "(all 50)" : `(${harvestNiches.length} selected)`}
                      </span>
                    </label>
                    {harvestNiches.length > 0 && (
                      <button onClick={() => setHarvestNiches([])} className="text-xs text-text-muted hover:text-danger transition-colors">
                        Clear
                      </button>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto p-2 bg-surface border border-border rounded-xl">
                    {NICHES.map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setHarvestNiches((prev) =>
                          prev.includes(n) ? prev.filter((x) => x !== n) : [...prev, n]
                        )}
                        className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${
                          harvestNiches.includes(n)
                            ? "bg-accent/20 border border-accent/50 text-text-primary"
                            : "bg-card border border-border text-text-muted hover:text-text-primary hover:border-border/60"
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>
                <button onClick={handleHarvest} disabled={harvesting}
                  className="gradient-btn text-white font-semibold px-6 py-2 rounded-xl disabled:opacity-50 text-sm">
                  {harvesting
                    ? "Harvesting…"
                    : harvestNiches.length === 1
                      ? `Harvest: ${harvestNiches[0].split(" ")[0]}`
                      : harvestNiches.length > 1
                        ? `Harvest ${harvestNiches.length} niches`
                        : `Run ${harvestPlatform === "instagram" ? "Instagram" : "TikTok"} Harvest`}
                </button>
              </div>

              {harvestNiches.length > 0 && (
                <p className="text-yellow-400/80 text-xs">
                  🎯 Targeting{" "}
                  {harvestNiches.length === 1
                    ? <strong>{harvestNiches[0]}</strong>
                    : <><strong>{harvestNiches.length} niches</strong>: {harvestNiches.join(", ")}</>
                  }{" "}
                  — raise max-per-niche for stress testing (e.g. 20).
                </p>
              )}

              {harvestError && <p className="text-danger text-sm">{harvestError}</p>}

              {(["tiktok", "instagram"] as const).map((p) => {
                const s = harvestStatus?.[p];
                if (!s || s.status === "never_run") return null;
                const isZeroAdded = (s.total_added ?? 0) === 0;
                const isDoneOrDegraded = s.status === "done" || s.status === "degraded";
                const detailOpen = harvestDetailExpanded[p] ?? false;
                const belowThreshold = (s.total_skip_below_min_views ?? 0) + (s.total_skip_below_min_likes ?? 0);

                return (
                  <div key={p} className={`rounded-xl px-4 py-3 text-sm border ${
                    s.status === "running" ? "bg-yellow-400/5 border-yellow-400/20"
                    : s.status === "failed" ? "bg-danger/5 border-danger/20"
                    : isZeroAdded ? "bg-yellow-400/5 border-yellow-400/20"
                    : "bg-success/5 border-success/20"
                  } text-text-primary`}>
                    <p className="text-xs text-text-muted/60 uppercase tracking-widest mb-1">
                      {p === "tiktok" ? "TikTok" : "Instagram"}
                    </p>

                    {s.status === "running" ? (
                      <div className="space-y-0.5 text-yellow-400">
                        <p>Harvest in progress — checking every 8s…</p>
                        {(s.niches_processed ?? 0) > 0 && (
                          <p className="text-xs opacity-70">
                            {s.niches_processed} niches done · +{s.total_added ?? 0} seeds
                            {(s.total_gemini_calls ?? 0) > 0 && ` · ${s.total_gemini_calls} Gemini calls`}
                          </p>
                        )}
                      </div>
                    ) : s.status === "failed" ? (
                      <div className="space-y-1 text-danger">
                        <p className="font-medium">Error — harvest failed</p>
                        {s.error && <p className="text-xs opacity-80 font-mono">{s.error}</p>}
                        {s.finished_at && <p className="text-xs opacity-60">{new Date(s.finished_at).toLocaleString()}</p>}
                      </div>
                    ) : isDoneOrDegraded ? (
                      <div className="space-y-1.5">
                        {isZeroAdded ? (
                          <p className="font-medium text-yellow-400">
                            Finished · +0 seeds added
                            {s.status === "degraded" ? " — errors prevented harvest" : " — all candidates filtered out"}
                          </p>
                        ) : (
                          <p className="font-medium text-success">Complete · +{s.total_added} seeds added</p>
                        )}
                        <p className="text-text-muted text-xs">
                          {s.niches_processed} niches · {s.total_skipped ?? 0} skipped
                          {s.finished_at && ` · ${new Date(s.finished_at).toLocaleString()}`}
                        </p>
                        {(s.total_gemini_calls ?? 0) > 0 && (
                          <p className="text-text-muted text-xs">
                            🤖 {s.total_gemini_calls} Gemini upload{(s.total_gemini_calls ?? 0) !== 1 ? "s" : ""} this run
                          </p>
                        )}

                        {isZeroAdded && (() => {
                          const dupCount = s.total_skip_duplicate ?? 0;
                          const missingFieldCount = (s.total_skip_missing_id ?? 0) + (s.total_skip_missing_play_url ?? 0) + (s.total_skip_missing_url ?? 0);
                          const noCandidates = (s.total_search_failures ?? 0) === 0 && belowThreshold === 0 && dupCount === 0 && missingFieldCount === 0 && (s.total_download_errors ?? 0) === 0 && (s.total_analysis_errors ?? 0) === 0;
                          return (
                            <div className="mt-1 bg-yellow-400/5 border border-yellow-400/20 rounded-lg px-3 py-2 space-y-1">
                              <p className="text-yellow-400 text-xs font-semibold">Why 0 seeds?</p>
                              {(s.total_search_failures ?? 0) > 0 && <p className="text-xs text-text-muted">• {s.total_search_failures} keyword search{(s.total_search_failures ?? 0) !== 1 ? "es" : ""} failed (API rate limit or unreachable)</p>}
                              {belowThreshold > 0 && <p className="text-xs text-text-muted">• {belowThreshold} candidate{belowThreshold !== 1 ? "s" : ""} below {p === "tiktok" ? "min views" : "min likes"} — lower the threshold or use Debug mode</p>}
                              {dupCount > 0 && <p className="text-xs text-text-muted">• {dupCount} duplicate{dupCount !== 1 ? "s" : ""} skipped — already in the seed library</p>}
                              {missingFieldCount > 0 && <p className="text-xs text-text-muted">• {missingFieldCount} candidate{missingFieldCount !== 1 ? "s" : ""} skipped — missing required fields</p>}
                              {(s.total_download_errors ?? 0) > 0 && <p className="text-xs text-text-muted">• {s.total_download_errors} download{(s.total_download_errors ?? 0) !== 1 ? "s" : ""} failed{s.last_download_error && <span className="block mt-0.5 font-mono text-[11px] text-text-muted/60 break-all">{s.last_download_error}</span>}</p>}
                              {(s.total_analysis_errors ?? 0) > 0 && <p className="text-xs text-text-muted">• {s.total_analysis_errors} Gemini analysis failure{(s.total_analysis_errors ?? 0) !== 1 ? "s" : ""}{s.last_analysis_error && <span className="block mt-0.5 font-mono text-[11px] text-text-muted/60 break-all">{s.last_analysis_error}</span>}</p>}
                              {(s.total_db_errors ?? 0) > 0 && <p className="text-xs text-text-muted">• {s.total_db_errors} database error{(s.total_db_errors ?? 0) !== 1 ? "s" : ""}{s.last_db_error && <span className="block mt-0.5 font-mono text-[11px] text-text-muted/60 break-all">{s.last_db_error}</span>}</p>}
                              {noCandidates && <p className="text-xs text-text-muted">• No candidates returned from search — {p === "tiktok" ? "tikwm" : "HikerAPI"} returned an empty result set</p>}
                            </div>
                          );
                        })()}

                        {!isZeroAdded && (s.total_errors ?? 0) > 0 && <p className="text-yellow-400 text-xs">⚠ {s.total_errors} video{(s.total_errors ?? 0) !== 1 ? "s" : ""} failed</p>}
                        {!isZeroAdded && (s.total_search_failures ?? 0) > 0 && <p className="text-yellow-400 text-xs">⚠ {s.total_search_failures} search{(s.total_search_failures ?? 0) !== 1 ? "es" : ""} failed — fewer seeds than expected</p>}
                        {(s.failed_niches ?? 0) > 0 && <p className="text-yellow-400 text-xs">⚠ {s.failed_niches} niche{(s.failed_niches ?? 0) !== 1 ? "s" : ""} crashed — check Railway logs</p>}

                        {s.detail && s.detail.length > 0 && (
                          <div className="mt-1">
                            <button onClick={() => setHarvestDetailExpanded(prev => ({ ...prev, [p]: !detailOpen }))} className="text-xs text-accent hover:underline">
                              {detailOpen ? "Hide" : "Show"} per-niche detail ({s.detail.length})
                            </button>
                            {detailOpen && (
                              <div className="mt-2 overflow-x-auto">
                                <table className="w-full text-xs border-collapse">
                                  <thead>
                                    <tr className="text-text-muted/60 border-b border-border/30">
                                      <th className="text-left py-1 pr-3 font-medium">Niche</th>
                                      <th className="text-right py-1 pr-2 font-medium">+Added</th>
                                      <th className="text-right py-1 pr-2 font-medium">Skip</th>
                                      <th className="text-right py-1 pr-2 font-medium">↓Filter</th>
                                      <th className="text-right py-1 pr-2 font-medium">Gemini</th>
                                      <th className="text-right py-1 pr-2 font-medium">Err</th>
                                      <th className="text-right py-1 font-medium">↯Srch</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {s.detail.map((d) => (
                                      <tr key={d.niche} className={`border-t border-border/20 ${d.added > 0 ? "text-success" : d.errors > 0 || (d.search_failures ?? 0) > 0 ? "text-yellow-400/80" : "text-text-muted"}`}>
                                        <td className="py-1 pr-3 text-text-primary/80" style={{ maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.niche}</td>
                                        <td className="py-1 pr-2 text-right font-medium">{d.added}</td>
                                        <td className="py-1 pr-2 text-right">{d.skipped}</td>
                                        <td className="py-1 pr-2 text-right">{(d.skip_below_min_views ?? 0) + (d.skip_below_min_likes ?? 0)}</td>
                                        <td className="py-1 pr-2 text-right">{d.gemini_calls ?? 0}</td>
                                        <td className="py-1 pr-2 text-right">{d.errors}</td>
                                        <td className="py-1 text-right">{d.search_failures ?? 0}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>

            {/* Trend Feed Harvest */}
            <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
              <div>
                <h2 className="text-text-primary font-semibold text-lg">Trend Feed Harvest</h2>
                <p className="text-text-muted text-sm mt-1">
                  Pulls TikTok videos published in the last <strong>N days</strong> that are already accumulating
                  views fast. Views per day is shown descriptively — a 500K view video in 7 days
                  is a very different signal than one from 6 months ago.
                </p>
              </div>

              <div className="flex flex-wrap gap-4 items-end">
                <div>
                  <label className="block text-xs text-text-muted mb-1">Max video age (days)</label>
                  <input type="number" min="7" max="90" value={trendMaxAge}
                    onChange={(e) => setTrendMaxAge(e.target.value)}
                    className="w-36 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-accent" />
                </div>
                <div>
                  <label className="block text-xs text-text-muted mb-1">Min velocity (views/day)</label>
                  <input type="number" min="1000" value={trendMinVelocity}
                    onChange={(e) => setTrendMinVelocity(e.target.value)}
                    className="w-40 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-accent" />
                </div>
                <button onClick={handleTrendHarvest} disabled={trendHarvesting}
                  className="gradient-btn text-white font-semibold px-6 py-2 rounded-xl disabled:opacity-50 text-sm">
                  {trendHarvesting ? "Harvesting trends…" : "Run Trend Harvest (TikTok)"}
                </button>
              </div>

              {trendHarvestError && <p className="text-danger text-sm">{trendHarvestError}</p>}

              {trendHarvestStatus && trendHarvestStatus.status !== "never_run" && (
                <div className={`rounded-xl px-4 py-3 text-sm border ${
                  trendHarvestStatus.status === "running" ? "bg-yellow-400/5 border-yellow-400/20 text-yellow-400"
                  : trendHarvestStatus.status === "failed" ? "bg-danger/5 border-danger/20 text-danger"
                  : "bg-success/5 border-success/20 text-text-primary"
                }`}>
                  {trendHarvestStatus.status === "running" ? (
                    <div className="space-y-0.5">
                      <p>Trend harvest in progress — checking every 8s…</p>
                      {(trendHarvestStatus.niches_processed ?? 0) > 0 && (
                        <p className="text-xs opacity-70">
                          {trendHarvestStatus.niches_processed} niches done · +{trendHarvestStatus.total_added ?? 0} trending seeds
                          {(trendHarvestStatus.total_gemini_calls ?? 0) > 0 && ` · ${trendHarvestStatus.total_gemini_calls} Gemini calls`}
                        </p>
                      )}
                    </div>
                  ) : trendHarvestStatus.status === "failed" ? (
                    <div>
                      <p className="font-medium">Trend harvest failed</p>
                      {trendHarvestStatus.error && <p className="text-xs opacity-80 font-mono mt-1">{trendHarvestStatus.error}</p>}
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <p className="font-medium text-success">Complete · +{trendHarvestStatus.total_added} trending seeds added</p>
                      <p className="text-text-muted text-xs">
                        {trendHarvestStatus.niches_processed} niches · {trendHarvestStatus.total_skipped} skipped
                        {trendHarvestStatus.finished_at && ` · ${new Date(trendHarvestStatus.finished_at).toLocaleString()}`}
                      </p>
                      {(trendHarvestStatus.total_gemini_calls ?? 0) > 0 && (
                        <p className="text-text-muted text-xs">🤖 {trendHarvestStatus.total_gemini_calls} Gemini video uploads used this run</p>
                      )}
                      {(trendHarvestStatus.total_errors ?? 0) > 0 && <p className="text-yellow-400 text-xs">⚠ {trendHarvestStatus.total_errors} failed — check Railway logs</p>}
                      {(trendHarvestStatus.total_search_failures ?? 0) > 0 && (
                        <p className="text-yellow-400 text-xs">
                          ⚠ {trendHarvestStatus.total_search_failures} search{trendHarvestStatus.total_search_failures !== 1 ? "es" : ""} failed (likely API rate limit)
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════
            INTELLIGENCE TAB
        ══════════════════════════════════════════════════ */}
        {mainTab === "intelligence" && (
          <div className="space-y-6">

            {/* Niche Intelligence */}
            <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
              <div>
                <h2 className="text-text-primary font-semibold text-lg">Niche Intelligence</h2>
                <p className="text-text-muted text-sm mt-1">
                  Synthesizes all rated seeds into a comprehensive pattern block per niche — including data-derived
                  dimension weights. Run after harvesting. Thinking/Deep analyses use this instead of raw seeds.
                </p>
              </div>

              <div className="flex flex-wrap gap-3 items-end">
                <div>
                  <label className="block text-xs text-text-muted mb-1">Niche (optional — blank = all)</label>
                  <select
                    value={insightNiche}
                    onChange={(e) => setInsightNiche(e.target.value)}
                    className="w-52 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-accent"
                  >
                    <option value="">All niches with ≥3 seeds</option>
                    {NICHES.map((n) => <option key={n} value={n} className="bg-card">{n}</option>)}
                  </select>
                </div>
                <button
                  onClick={handleGenerateInsights}
                  disabled={generatingInsights}
                  className="gradient-btn text-white font-semibold px-6 py-2 rounded-xl disabled:opacity-50 text-sm"
                >
                  {generatingInsights
                    ? "Synthesizing…"
                    : insightNiche
                      ? `Generate for ${insightNiche}`
                      : `Generate All (${activePlatform === "tiktok" ? "TikTok" : "Instagram"})`}
                </button>
              </div>

              {insightError && <p className="text-danger text-sm">{insightError}</p>}

              {insightResult && (
                <div className="bg-surface border border-border rounded-xl px-4 py-3 text-sm space-y-1">
                  <p className="text-text-primary font-medium">
                    Generated {insightResult.generated} / {insightResult.total} niches
                  </p>
                  <div className="space-y-0.5 max-h-40 overflow-y-auto">
                    {insightResult.results.map((r) => (
                      <p key={r.niche} className={`text-xs ${r.status === "generated" ? "text-success" : r.status === "error" ? "text-danger" : "text-text-muted"}`}>
                        {r.status === "generated" ? "✓" : r.status === "error" ? "✗" : "–"}{" "}
                        {r.niche}
                        {r.status === "generated" && r.seed_count != null && (
                          ` (${r.seed_count} seeds${r.correction_count ? ` + ${r.correction_count} corrections` : ""})`
                        )}
                        {r.status === "skipped" && r.reason && ` — ${r.reason}`}
                        {r.status === "error" && r.reason && `: ${r.reason}`}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {insights.length > 0 && (
                <div>
                  <p className="text-text-muted text-xs uppercase tracking-widest font-semibold mb-2">
                    Generated — {activePlatform === "tiktok" ? "TikTok" : "Instagram"} ({insights.length})
                  </p>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {insights.map((ins) => (
                      <div key={ins.niche} className="bg-surface border border-border rounded-xl px-4 py-3">
                        <div className="flex justify-between items-center gap-2 mb-1">
                          <span className="text-text-primary text-sm font-medium">{ins.niche}</span>
                          <span className="text-text-muted text-xs flex-shrink-0">
                            {ins.seed_count} seeds · {new Date(ins.generated_at).toLocaleDateString()}
                          </span>
                        </div>
                        <p className="text-text-muted text-xs leading-relaxed line-clamp-2">{ins.insight_preview}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {insights.length === 0 && !generatingInsights && (
                <p className="text-text-muted text-sm text-center py-4">
                  No insights generated yet. Run after harvesting seeds.
                </p>
              )}
            </div>

            {/* Trend Intelligence */}
            <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
              <div>
                <h2 className="text-text-primary font-semibold text-lg">Trend Intelligence</h2>
                <p className="text-text-muted text-sm mt-1">
                  Synthesizes what has <strong>changed</strong> in the last 30 days — compares recent seeds
                  vs established ones to detect rising formats, fading patterns, and velocity signals.
                  Injected into Thinking/Deep analyses alongside niche intelligence. Expires after 7 days.
                </p>
              </div>

              <div className="flex flex-wrap gap-3 items-end">
                <div>
                  <label className="block text-xs text-text-muted mb-1">Niche (optional — blank = all)</label>
                  <select value={trendNiche} onChange={(e) => setTrendNiche(e.target.value)}
                    className="w-52 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-accent">
                    <option value="">All niches with recent seeds</option>
                    {NICHES.map((n) => <option key={n} value={n} className="bg-card">{n}</option>)}
                  </select>
                </div>
                <button onClick={handleGenerateTrends} disabled={generatingTrends}
                  className="gradient-btn text-white font-semibold px-6 py-2 rounded-xl disabled:opacity-50 text-sm">
                  {generatingTrends
                    ? "Analyzing trends…"
                    : trendNiche
                      ? `Generate for ${trendNiche}`
                      : `Generate All (${activePlatform === "tiktok" ? "TikTok" : "Instagram"})`}
                </button>
              </div>

              {trendError && <p className="text-danger text-sm">{trendError}</p>}

              {trendResult && (
                <div className="bg-surface border border-border rounded-xl px-4 py-3 text-sm space-y-1">
                  <p className="text-text-primary font-medium">
                    Generated {trendResult.generated} / {trendResult.total} niches
                  </p>
                  <div className="space-y-0.5 max-h-40 overflow-y-auto">
                    {trendResult.results.map((r) => (
                      <p key={r.niche} className={`text-xs ${r.status === "generated" ? "text-success" : r.status === "error" ? "text-danger" : "text-text-muted"}`}>
                        {r.status === "generated" ? "✓" : r.status === "error" ? "✗" : "–"}{" "}
                        {r.niche}
                        {r.status === "generated" && r.recent_count != null && ` (${r.recent_count} recent seeds)`}
                        {r.status === "skipped" && r.reason && ` — ${r.reason}`}
                        {r.status === "error" && r.reason && `: ${r.reason}`}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {trends.length > 0 && (
                <div>
                  <p className="text-text-muted text-xs uppercase tracking-widest font-semibold mb-2">
                    Active — {activePlatform === "tiktok" ? "TikTok" : "Instagram"} ({trends.length})
                  </p>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {trends.map((t) => {
                      const age = Math.floor((Date.now() - new Date(t.generated_at).getTime()) / 86400000);
                      const stale = age >= 7;
                      return (
                        <div key={t.niche} className={`bg-surface border rounded-xl px-4 py-3 ${stale ? "border-yellow-400/30" : "border-border"}`}>
                          <div className="flex justify-between items-center gap-2 mb-1">
                            <span className="text-text-primary text-sm font-medium">{t.niche}</span>
                            <span className={`text-xs flex-shrink-0 ${stale ? "text-yellow-400" : "text-text-muted"}`}>
                              {t.recent_seed_count} recent · {t.established_seed_count} established
                              {" · "}{stale ? `⚠ ${age}d old` : `${age}d old`}
                            </span>
                          </div>
                          <p className="text-text-muted text-xs leading-relaxed line-clamp-2">{t.trend_preview}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {trends.length === 0 && !generatingTrends && (
                <p className="text-text-muted text-sm text-center py-4">
                  No trend summaries yet. Run Trend Harvest first, then generate here.
                </p>
              )}
            </div>
          </div>
        )}

      </div>
    </main>
  );
}
