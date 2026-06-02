"use client";

import { useState, useEffect, useCallback } from "react";
import {
  getAdminSeeds,
  addSeedVideo,
  deleteSeedVideo,
  seedFromUrl,
  getFetchStatus,
  ackFetchStatus,
  SeedVideoOut,
  FetchStatus,
} from "@/lib/api";

const NICHES = [
  "Fitness",
  "Comedy",
  "Food",
  "Fashion",
  "Education",
  "Gaming",
  "Lifestyle",
  "Other",
];

export default function AdminPage() {
  const [password, setPassword] = useState("");
  const [authed, setAuthed] = useState(false);
  const [authError, setAuthError] = useState("");
  const [seeds, setSeeds] = useState<SeedVideoOut[]>([]);
  const [loadError, setLoadError] = useState("");

  // Form state
  const [file, setFile] = useState<File | null>(null);
  const [niche, setNiche] = useState("Fitness");
  const [viewCount, setViewCount] = useState("");
  const [likeCount, setLikeCount] = useState("");
  const [performed, setPerformed] = useState(true);
  const [notes, setNotes] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

  // URL fetch state
  const [fetchUrl, setFetchUrl] = useState("");
  const [fetchNiche, setFetchNiche] = useState("Fitness");
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState("");
  const [fetchStatus, setFetchStatus] = useState<FetchStatus | null>(null);

  const refreshFetchStatus = useCallback(async (pw: string) => {
    try {
      const status = await getFetchStatus(pw);
      setFetchStatus(status);
    } catch {
      // Non-fatal — just don't show a banner.
    }
  }, []);

  const loadSeeds = useCallback(
    async (pw: string) => {
      try {
        const data = await getAdminSeeds(pw);
        setSeeds(data);
        setLoadError("");
      } catch (err: unknown) {
        setLoadError(err instanceof Error ? err.message : "Failed to load seeds");
      }
    },
    []
  );

  useEffect(() => {
    const saved = localStorage.getItem("viraliq_admin_pw");
    if (saved) {
      setPassword(saved);
      setAuthed(true);
      loadSeeds(saved);
      refreshFetchStatus(saved);
    }
  }, [loadSeeds, refreshFetchStatus]);

  async function handleAuth(e: React.FormEvent) {
    e.preventDefault();
    try {
      await getAdminSeeds(password);
      localStorage.setItem("viraliq_admin_pw", password);
      setAuthed(true);
      setAuthError("");
      loadSeeds(password);
      refreshFetchStatus(password);
    } catch {
      setAuthError("Invalid password.");
    }
  }

  async function handleFetchFromUrl(e: React.FormEvent) {
    e.preventDefault();
    if (!fetchUrl.trim()) return;
    setFetching(true);
    setFetchError("");
    try {
      await seedFromUrl(fetchUrl.trim(), fetchNiche, password);
      setFetchUrl("");
      await loadSeeds(password);
      await refreshFetchStatus(password);
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Fetch failed");
      await refreshFetchStatus(password);
    } finally {
      setFetching(false);
    }
  }

  async function dismissFetchWarning() {
    setFetchStatus({ broken: false });
    try {
      await ackFetchStatus(password);
    } catch {
      // ignore
    }
  }

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("niche", niche);
      form.append("view_count", viewCount);
      form.append("like_count", likeCount);
      form.append("performed", String(performed));
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
            {authError && (
              <p className="text-danger text-sm">{authError}</p>
            )}
            <button
              type="submit"
              className="w-full gradient-btn text-white font-semibold py-3 rounded-xl"
            >
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
          <span className="font-bold gradient-text">ViralIQ Admin</span>
          <button
            onClick={handleLogout}
            className="text-text-muted text-sm hover:text-danger transition-colors"
          >
            Sign out
          </button>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">
        {/* Scraper-failure warning banner */}
        {fetchStatus?.broken && (
          <div className="bg-danger/10 border border-danger/40 rounded-2xl p-4 flex items-start justify-between gap-4">
            <div className="text-sm text-text-primary">
              <p className="font-semibold text-danger mb-1">⚠️ Auto-fetch last failed</p>
              <p className="text-text-muted">
                {fetchStatus.when
                  ? new Date(fetchStatus.when).toLocaleString()
                  : ""}
                {fetchStatus.message ? `: ${fetchStatus.message}` : ""}
              </p>
              <p className="text-text-muted mt-1">
                TikTok may have changed — try{" "}
                <code className="bg-surface px-1.5 py-0.5 rounded text-text-primary">
                  pip install -U yt-dlp
                </code>
                ; if it still fails the extractor code needs updating.
              </p>
            </div>
            <button
              onClick={dismissFetchWarning}
              className="flex-shrink-0 text-text-muted hover:text-text-primary text-sm"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Fetch from TikTok link */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <h2 className="text-text-primary font-semibold text-lg mb-1">
            Fetch from TikTok link
          </h2>
          <p className="text-text-muted text-sm mb-4">
            Paste a public TikTok URL — views, likes, and caption are pulled in
            automatically. (Local use only; TikTok blocks server IPs.)
          </p>
          <form
            onSubmit={handleFetchFromUrl}
            className="flex flex-col md:flex-row gap-3 md:items-end"
          >
            <div className="flex-1">
              <label className="block text-sm text-text-muted mb-1">
                TikTok URL
              </label>
              <input
                type="url"
                placeholder="https://www.tiktok.com/@user/video/123..."
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
                className="w-full md:w-auto bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary focus:outline-none focus:border-purple-to"
              >
                {NICHES.map((n) => (
                  <option key={n} value={n} className="bg-card">
                    {n}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="submit"
              disabled={fetching}
              className="gradient-btn text-white font-semibold px-6 py-2.5 rounded-xl disabled:opacity-50 whitespace-nowrap"
            >
              {fetching ? "Fetching..." : "Fetch & Save"}
            </button>
          </form>
          {fetchError && <p className="text-danger text-sm mt-2">{fetchError}</p>}
        </div>

        {/* Upload form (manual fallback) */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <h2 className="text-text-primary font-semibold text-lg mb-5">
            Add Seed Video Manually
          </h2>
          <form onSubmit={handleUpload} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-text-muted mb-1">
                  Video file
                </label>
                <input
                  type="file"
                  accept=".mp4,.mov"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="w-full text-text-muted text-sm file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-surface file:text-text-primary file:cursor-pointer"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-text-muted mb-1">
                  Niche
                </label>
                <select
                  value={niche}
                  onChange={(e) => setNiche(e.target.value)}
                  className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary focus:outline-none focus:border-purple-to"
                >
                  {NICHES.map((n) => (
                    <option key={n} value={n} className="bg-card">
                      {n}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-text-muted mb-1">
                  View count
                </label>
                <input
                  type="number"
                  min="0"
                  placeholder="e.g. 50000"
                  value={viewCount}
                  onChange={(e) => setViewCount(e.target.value)}
                  required
                  className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
                />
              </div>
              <div>
                <label className="block text-sm text-text-muted mb-1">
                  Like count
                </label>
                <input
                  type="number"
                  min="0"
                  placeholder="e.g. 3000"
                  value={likeCount}
                  onChange={(e) => setLikeCount(e.target.value)}
                  required
                  className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-text-muted mb-2">
                Performance
              </label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="performed"
                    checked={performed}
                    onChange={() => setPerformed(true)}
                    className="accent-success"
                  />
                  <span className="text-success text-sm font-medium">
                    🚀 Viral (10k+ views)
                  </span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="performed"
                    checked={!performed}
                    onChange={() => setPerformed(false)}
                    className="accent-danger"
                  />
                  <span className="text-danger text-sm font-medium">
                    📉 Flopped (&lt;1k views)
                  </span>
                </label>
              </div>
            </div>

            <div>
              <label className="block text-sm text-text-muted mb-1">
                Notes (optional)
              </label>
              <textarea
                placeholder="e.g. Strong hook, trending audio, mid-roll drop off..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                className="w-full bg-surface border border-border rounded-xl px-4 py-2.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to resize-none"
              />
            </div>

            {uploadError && (
              <p className="text-danger text-sm">{uploadError}</p>
            )}

            <button
              type="submit"
              disabled={uploading}
              className="gradient-btn text-white font-semibold px-6 py-2.5 rounded-xl disabled:opacity-50"
            >
              {uploading ? "Uploading..." : "Add Seed Video"}
            </button>
          </form>
        </div>

        {/* Seed table */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <div className="flex justify-between items-center mb-5">
            <h2 className="text-text-primary font-semibold text-lg">
              Seed Videos
            </h2>
            <span className="text-text-muted text-sm bg-surface border border-border px-3 py-1 rounded-full">
              {seeds.length} video{seeds.length !== 1 ? "s" : ""} in database
            </span>
          </div>

          {loadError && (
            <p className="text-danger text-sm mb-4">{loadError}</p>
          )}

          {seeds.length === 0 ? (
            <p className="text-text-muted text-sm text-center py-8">
              No seed videos yet. Add some above.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-text-muted border-b border-border">
                    <th className="text-left py-2 pr-4">Niche</th>
                    <th className="text-right py-2 pr-4">Views</th>
                    <th className="text-right py-2 pr-4">Likes</th>
                    <th className="text-left py-2 pr-4">Status</th>
                    <th className="text-left py-2 pr-4">Notes</th>
                    <th className="text-left py-2 pr-4">Date</th>
                    <th className="text-right py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {seeds.map((seed) => (
                    <tr
                      key={seed.id}
                      className="border-b border-border/50 hover:bg-surface/50 transition-colors"
                    >
                      <td className="py-2.5 pr-4 text-text-primary font-medium">
                        {seed.niche}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-text-primary">
                        {seed.view_count.toLocaleString()}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-text-muted">
                        {seed.like_count.toLocaleString()}
                      </td>
                      <td className="py-2.5 pr-4">
                        {seed.performed ? (
                          <span className="text-success text-xs font-medium bg-success/10 px-2 py-0.5 rounded-full">
                            Viral
                          </span>
                        ) : (
                          <span className="text-danger text-xs font-medium bg-danger/10 px-2 py-0.5 rounded-full">
                            Flopped
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4 text-text-muted max-w-[180px] truncate">
                        {seed.notes || "—"}
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
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
