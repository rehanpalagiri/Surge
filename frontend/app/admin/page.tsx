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
  SeedVideoOut,
  FetchStatus,
  ApiUsage,
  HarvestStatus,
} from "@/lib/api";

// Must stay in sync with CANONICAL_NICHES in backend/services/niche_classifier.py —
// seed matching is an exact string compare against the classified user niche.
const NICHES = [
  // Original 20
  "Fitness & Gym",
  "Comedy & Skits",
  "Food & Cooking",
  "Fashion & Style",
  "Beauty & Makeup",
  "Education & Tutorials",
  "Gaming",
  "Music & Dance",
  "Tech & Gadgets",
  "Finance & Investing",
  "Health & Wellness",
  "Travel & Adventure",
  "Lifestyle & Vlogs",
  "Motivation & Mindset",
  "Sports & Athletics",
  "Relationships & Dating",
  "Art & Creativity",
  "Business & Entrepreneurship",
  "Pets & Animals",
  "Parenting & Family",
  // Extended 30
  "Skincare & Glow",
  "Weight Loss Journey",
  "Yoga & Meditation",
  "Baking & Desserts",
  "Vegan & Plant-Based",
  "DIY & Crafts",
  "Home Decor & Interior",
  "Cleaning & Organization",
  "Career & Job Tips",
  "Real Estate",
  "Side Hustles",
  "Crypto & Web3",
  "Outdoor & Hiking",
  "True Crime & Mystery",
  "Books & Reading",
  "Astrology & Spirituality",
  "Movies & TV",
  "Cars & Automotive",
  "Photography & Editing",
  "Sustainability & Eco",
  "Mental Health",
  "Cooking on a Budget",
  "Couples & Romance",
  "College & Student Life",
  "Luxury & Wealth",
  "Street Style & Thrift",
  "Hair Care & Styling",
  "Kids & Baby",
  "ASMR & Relaxation",
  "News & Commentary",
];

type Tab = "url" | "manual";
type Platform = "tiktok" | "instagram";

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
  const [authed, setAuthed] = useState(false);
  const [authError, setAuthError] = useState("");
  const [seeds, setSeeds] = useState<SeedVideoOut[]>([]);
  const [loadError, setLoadError] = useState("");
  const [tab, setTab] = useState<Tab>("url");
  const [activePlatform, setActivePlatform] = useState<Platform>("tiktok");

  // URL fetch state
  const [fetchUrl, setFetchUrl] = useState("");
  const [fetchNiche, setFetchNiche] = useState("Fitness & Gym");
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState("");
  const [fetchStatus, setFetchStatus] = useState<FetchStatus | null>(null);
  const [apiUsage, setApiUsage] = useState<ApiUsage | null>(null);

  // Harvest state
  const [harvestStatus, setHarvestStatus] = useState<HarvestStatus | null>(null);
  const [harvesting, setHarvesting] = useState(false);
  const [harvestError, setHarvestError] = useState("");
  const [harvestMinViews, setHarvestMinViews] = useState("500000");
  const [harvestMinLikes, setHarvestMinLikes] = useState("1000");
  const [harvestMaxPer, setHarvestMaxPer] = useState("3");
  const [harvestPlatform, setHarvestPlatform] = useState<"tiktok" | "instagram">("tiktok");

  // Manual upload state
  const [file, setFile] = useState<File | null>(null);
  const [niche, setNiche] = useState("Fitness & Gym");
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
    }
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem("viraliq_admin_pw");
    if (saved) {
      setPassword(saved);
      setAuthed(true);
      loadSeeds(saved);
      refreshFetchStatus(saved);
      refreshApiUsage(saved);
      refreshHarvestStatus(saved);
    }
  }, [loadSeeds, refreshFetchStatus, refreshApiUsage, refreshHarvestStatus]);

  // Reset view count when switching platforms
  useEffect(() => {
    setViewCount("");
  }, [activePlatform]);

  async function handleAuth(e: React.FormEvent) {
    e.preventDefault();
    try {
      await getAdminSeeds(password);
      localStorage.setItem("viraliq_admin_pw", password);
      setAuthed(true);
      setAuthError("");
      loadSeeds(password);
      refreshFetchStatus(password);
      refreshApiUsage(password);
      refreshHarvestStatus(password);
    } catch { setAuthError("Invalid password."); }
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
        min_likes: parseInt(harvestMinLikes) || 1_000,
        max_per_niche: parseInt(harvestMaxPer) || 3,
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

  function handleLogout() {
    localStorage.removeItem("viraliq_admin_pw");
    setAuthed(false);
    setPassword("");
    setSeeds([]);
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
              className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
            />
            {authError && <p className="text-danger text-sm">{authError}</p>}
            <button type="submit" className="w-full gradient-btn text-white font-semibold py-3 rounded-xl">
              Sign In
            </button>
          </form>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <nav className="border-b border-border bg-surface/50 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex justify-between items-center">
          <span className="font-bold gradient-text">Surge Admin</span>
          <button onClick={handleLogout} className="text-text-muted text-sm hover:text-danger transition-colors">
            Sign out
          </button>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">

        {/* API failure banner */}
        {fetchStatus?.broken && (
          <div className="bg-danger/10 border border-danger/40 rounded-2xl p-4 flex items-start justify-between gap-4">
            <div className="text-sm text-text-primary">
              <p className="font-semibold text-danger mb-1">⚠️ Auto-fetch last failed</p>
              <p className="text-text-muted">
                {fetchStatus.when ? new Date(fetchStatus.when).toLocaleString() : ""}
                {fetchStatus.message ? `: ${fetchStatus.message}` : ""}
              </p>
              <p className="text-text-muted mt-1">
                Use Manual Upload below as a fallback, or retry the URL.
              </p>
            </div>
            <button onClick={dismissFetchWarning} className="flex-shrink-0 text-text-muted hover:text-text-primary text-sm">
              Dismiss
            </button>
          </div>
        )}

        {/* Add seed card */}
        <div className="bg-card border border-border rounded-2xl overflow-hidden">

          {/* Platform selector */}
          <div className="flex items-center gap-1 px-4 pt-4 pb-3 border-b border-border">
            <span className="text-text-muted text-xs font-medium mr-2 uppercase tracking-widest">Platform</span>
            {(["tiktok", "instagram"] as Platform[]).map((p) => (
              <button
                key={p}
                onClick={() => setActivePlatform(p)}
                className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-all ${
                  activePlatform === p
                    ? "bg-purple-from/15 border border-purple-to/40 text-text-primary"
                    : "text-text-muted hover:text-text-primary hover:bg-surface/60"
                }`}
              >
                {p === "tiktok" ? "TikTok" : "Instagram"}
              </button>
            ))}
          </div>

          {/* URL / Manual tab bar */}
          <div className="flex border-b border-border">
            {(["url", "manual"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex-1 py-3 text-sm font-medium transition-colors ${
                  tab === t
                    ? "text-text-primary border-b-2 border-purple-to bg-card"
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

                {/* Instagram usage counter */}
                {activePlatform === "instagram" && apiUsage && (
                  <UsageBar used={igUsed} limit={igLimit} resetsAt={igResetsAt} />
                )}

                {/* Limit reached warning */}
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
                      className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-text-muted mb-1">Niche</label>
                    <select
                      value={fetchNiche}
                      onChange={(e) => setFetchNiche(e.target.value)}
                      className="w-full md:w-48 bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary focus:outline-none focus:border-purple-to"
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
                        className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary focus:outline-none focus:border-purple-to"
                      >
                        {NICHES.map((n) => <option key={n} value={n} className="bg-card">{n}</option>)}
                    </select>
                    </div>

                    {/* View count — TikTok only */}
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
                          className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
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
                        className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
                      />
                    </div>
                  </div>

                  <div className="bg-surface/60 border border-border rounded-xl px-4 py-3 text-xs text-text-muted">
                    Surge sends this video to Gemini and generates a causal performance writeup
                    + a 0–10 virality rating (~20–30s). The video file is deleted afterward. If
                    analysis fails, the seed is not saved — just retry.
                  </div>

                  <div>
                    <label className="block text-sm text-text-muted mb-1">Notes (optional)</label>
                    <textarea
                      placeholder="e.g. Strong hook, trending audio, mid-roll drop off..."
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      rows={2}
                      className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to resize-none"
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

        {/* Door A: Auto-harvest card */}
        <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-text-primary font-semibold text-lg">Auto-Harvest Seeds</h2>
              <p className="text-text-muted text-sm mt-1">
                TikTok: searches via tikwm (free, unlimited). Instagram: searches via HikerAPI (requires HIKERAPI_KEY env var, 100 free requests).
              </p>
            </div>
            <span className="flex-shrink-0 text-[10px] font-semibold text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded-full whitespace-nowrap">
              🤖 Door A
            </span>
          </div>

          {/* Platform toggle */}
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
              <div>
                <label className="block text-xs text-text-muted mb-1">Min views</label>
                <input type="number" value={harvestMinViews}
                  onChange={(e) => setHarvestMinViews(e.target.value)}
                  className="w-36 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-purple-to" />
              </div>
            ) : (
              <div>
                <label className="block text-xs text-text-muted mb-1">Min likes</label>
                <input type="number" value={harvestMinLikes}
                  onChange={(e) => setHarvestMinLikes(e.target.value)}
                  className="w-36 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-purple-to" />
              </div>
            )}
            <div>
              <label className="block text-xs text-text-muted mb-1">Max per niche</label>
              <input type="number" min="1" max="10" value={harvestMaxPer}
                onChange={(e) => setHarvestMaxPer(e.target.value)}
                className="w-28 bg-surface border border-border rounded-xl px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-purple-to" />
            </div>
            <button onClick={handleHarvest} disabled={harvesting}
              className="gradient-btn text-white font-semibold px-6 py-2 rounded-xl disabled:opacity-50 text-sm">
              {harvesting ? "Harvesting…" : `Run ${harvestPlatform === "instagram" ? "Instagram" : "TikTok"} Harvest`}
            </button>
          </div>

          {harvestError && <p className="text-danger text-sm">{harvestError}</p>}

          {/* Status for each platform */}
          {(["tiktok", "instagram"] as const).map((p) => {
            const s = harvestStatus?.[p];
            if (!s || s.status === "never_run") return null;
            return (
              <div key={p} className={`rounded-xl px-4 py-3 text-sm border ${
                s.status === "running" ? "bg-yellow-400/5 border-yellow-400/20 text-yellow-400"
                : s.status === "failed" ? "bg-danger/5 border-danger/20 text-danger"
                : "bg-success/5 border-success/20 text-text-primary"
              }`}>
                <p className="text-xs text-text-muted/60 uppercase tracking-widest mb-1">{p === "tiktok" ? "TikTok" : "Instagram"}</p>
                {s.status === "running" ? (
                  <p>Harvest in progress — checking every 8s…</p>
                ) : s.status === "failed" ? (
                  <div className="space-y-1">
                    <p className="font-medium">Error — harvest failed</p>
                    {s.error && <p className="text-xs opacity-80 font-mono">{s.error}</p>}
                    {s.finished_at && <p className="text-xs opacity-60">{new Date(s.finished_at).toLocaleString()}</p>}
                  </div>
                ) : (
                  <div className="space-y-1">
                    <p className="font-medium text-success">Complete · +{s.total_added} seeds added</p>
                    <p className="text-text-muted text-xs">
                      {s.niches_processed} niches · {s.total_skipped} skipped
                      {s.finished_at && ` · ${new Date(s.finished_at).toLocaleString()}`}
                    </p>
                    {(s.total_errors ?? 0) > 0 && (
                      <p className="text-yellow-400 text-xs mt-1">
                        ⚠ {s.total_errors} video{s.total_errors !== 1 ? "s" : ""} failed — check Render logs
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Seed table */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <div className="flex justify-between items-center mb-5">
            <h2 className="text-text-primary font-semibold text-lg">Seed Videos</h2>
            <span className="text-text-muted text-sm bg-surface border border-border px-3 py-1 rounded-full">
              {seeds.length} video{seeds.length !== 1 ? "s" : ""}
            </span>
          </div>

          {loadError && <p className="text-danger text-sm mb-4">{loadError}</p>}

          {seeds.length === 0 ? (
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
                    <th className="text-center py-2 pr-4">Rating</th>
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
                                <span
                                  title="Auto-promoted from a verified user-posted video"
                                  className="text-[10px] font-semibold text-purple-to bg-purple-to/10 px-1.5 py-0.5 rounded-full"
                                >
                                  👤 user
                                </span>
                              )}
                              {seed.source === "harvest" && (
                                <span
                                  title="Auto-harvested via keyword search"
                                  className="text-[10px] font-semibold text-emerald-400 bg-emerald-400/10 px-1.5 py-0.5 rounded-full"
                                >
                                  🤖 auto
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
                              <button
                                onClick={() => setExpandedId(isOpen ? null : seed.id)}
                                className="text-purple-to hover:underline text-xs"
                              >
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
                            <button
                              onClick={() => handleDelete(seed.id)}
                              className="text-danger/60 hover:text-danger text-xs transition-colors"
                            >
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
    </main>
  );
}
