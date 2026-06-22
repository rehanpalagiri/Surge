import { getToken } from "./auth";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(token?: string | null): Record<string, string> {
  const t = token ?? getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export interface UserProfile {
  id: number;
  user_id: number;
  platform: string;
  handle: string | null;
  display_name: string | null;
  bio: string | null;
  target_audience: string | null;
  niche: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserProfileIn {
  handle?: string;
  display_name?: string;
  bio?: string;
  target_audience?: string;
  niche?: string;
}

export interface AnalysisOut {
  id: number;
  platform: string;
  filename: string;
  niche: string;
  caption: string | null;
  bio: string | null;
  scores_json: {
    overall_score: number;
    hook_velocity: number;
    cut_frequency: number;
    text_scannability: number;
    curiosity_gap: number;
    audio_visual_sync: number;
    loop_seamlessness: number;
    predicted_views: string;
    predicted_likes?: string;
    strengths: string[];
    improvements: string[];
    verdict: string;
    analysis_summary: string;
    improvement_plan?: ImprovementItem[];
    caption_rewrite?: string;
    hook_rewrite?: string;
    projected_verdict?: string;
    projected_views?: string;
    projected_likes?: string;
    first_improvement?: ImprovementItem | null;
    locked?: boolean;
    error?: string;
  };
  verdict: string;
  actual_views: number | null;
  actual_likes: number | null;
  video_url?: string | null;          // posted TikTok link (counts auto-fetched)
  counts_fetched_at?: string | null;
  pending_seed_consent?: boolean;     // owner's consent is "ask" — show the banner
  mode?: string;
  created_at: string;
}

export interface AnalysisSummary {
  id: number;
  platform: string;
  niche: string;
  verdict: string;
  overall_score: number | null;
  predicted_views: string | null;
  caption_preview: string | null;
  actual_views: number | null;
  actual_likes: number | null;
  video_url?: string | null;
  counts_fetched_at?: string | null;
  mode?: string;
  created_at: string;
}

export interface TokenOut {
  access_token: string;
  token_type: string;
}

export interface UserOut {
  id: number;
  username: string;
  email?: string | null;
  birth_year?: number | null;
  birth_date?: string | null;
  seed_consent?: "yes" | "no" | "ask";
  is_minor?: boolean;
  created_at: string;
}

export interface ImprovementItem {
  area: string;
  priority: number;
  current_score: number;
  problem: string;
  fix: string;
  pattern?: string;  // technique name, e.g. "cold open", "text-first frame"
  example?: string;  // legacy field — present on older analyses only
}

export interface SeedVideoOut {
  id: number;
  filename: string;
  platform: string;
  niche: string;
  view_count: number | null;   // null for Instagram seeds (platform hides views)
  like_count: number;
  rating: number | null;
  gemini_analysis: string | null; // raw JSON; parse for seed_summary
  notes: string | null;
  posted_at?: string | null;
  source?: string | null; // "admin" | "user" (auto-promoted from a verified link)
  created_at: string;
}

export interface ApiUsage {
  instagram: {
    used: number;
    limit: number;
    resets_at: string; // "YYYY-MM-DD"
  };
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

/** Pull the human-readable `detail` out of an API error for display. */
export function apiErrorDetail(err: unknown, fallback: string): string {
  const msg = err instanceof Error ? err.message : "";
  const jsonPart = msg.match(/\{.*\}$/);
  if (jsonPart) {
    try {
      const detail = JSON.parse(jsonPart[0])?.detail;
      if (typeof detail === "string") return detail;
    } catch {
      // not JSON — fall through
    }
  }
  // Non-JSON bodies (e.g. a gateway's HTML error page when the backend is
  // down) aren't fit to show users — only pass through short plain messages.
  if (msg && msg.length <= 160 && !msg.includes("<")) return msg;
  return fallback;
}

/**
 * Ping /health before kicking off the real upload so mobile Safari doesn't
 * drop the multipart request if the backend is mid-restart. Railway stays
 * always-on so 20s covers the worst-case container restart; 90s was Render-era.
 */
export async function wakeBackend(maxWaitMs: number = 20_000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    try {
      const res = await fetch(`${BASE}/health`, { cache: "no-store" });
      if (res.ok) return true;
    } catch {
      // Backend still asleep / unreachable — fall through and retry.
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  return false;
}

export async function analyzeVideo(
  file: File | null,
  niche: string,
  caption: string = "",
  bio: string = "",
  platform: string = "tiktok",
  videoUrl: string = "",
  secondary: string = ""
): Promise<{ id: number }> {
  const form = new FormData();
  if (file) form.append("file", file);
  if (videoUrl) form.append("video_url", videoUrl);
  form.append("niche", niche);
  if (secondary) form.append("secondary", secondary);
  form.append("caption", caption);
  form.append("bio", bio);
  form.append("platform", platform);
  const res = await fetch(`${BASE}/api/analyze`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return handleResponse<AnalysisOut>(res).then((a) => ({ id: a.id }));
}

export async function getProfile(platform: string): Promise<UserProfile | null> {
  const res = await fetch(`${BASE}/api/me/profile/${platform}`, {
    headers: authHeaders(),
  });
  if (res.status === 404) return null;
  return handleResponse<UserProfile>(res);
}

export async function upsertProfile(
  platform: string,
  data: UserProfileIn
): Promise<UserProfile> {
  const res = await fetch(`${BASE}/api/me/profile/${platform}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(data),
  });
  return handleResponse<UserProfile>(res);
}

export async function getAnalysis(
  id: string | number,
  token?: string | null
): Promise<AnalysisOut> {
  const res = await fetch(`${BASE}/api/analyses/${id}`, {
    headers: authHeaders(token),
  });
  return handleResponse<AnalysisOut>(res);
}

export async function signup(
  email: string,
  username: string,
  password: string,
  birthDate: string  // ISO YYYY-MM-DD
): Promise<TokenOut> {
  const res = await fetch(`${BASE}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, username, password, birth_date: birthDate }),
  });
  return handleResponse<TokenOut>(res);
}

export async function login(
  username: string,
  password: string
): Promise<TokenOut> {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return handleResponse<TokenOut>(res);
}

export async function getMe(token?: string | null): Promise<UserOut> {
  const res = await fetch(`${BASE}/api/auth/me`, {
    headers: authHeaders(token),
  });
  return handleResponse<UserOut>(res);
}

export async function getMyAnalyses(
  token?: string | null
): Promise<AnalysisSummary[]> {
  const res = await fetch(`${BASE}/api/me/analyses`, {
    headers: authHeaders(token),
  });
  return handleResponse<AnalysisSummary[]>(res);
}

export async function claimAnalysis(
  id: string | number,
  token?: string | null
): Promise<AnalysisOut> {
  const res = await fetch(`${BASE}/api/analyses/${id}/claim`, {
    method: "POST",
    headers: authHeaders(token),
  });
  return handleResponse<AnalysisOut>(res);
}

export async function submitFeedback(
  id: string | number,
  actualViews: number | undefined,
  actualLikes?: number
): Promise<AnalysisOut> {
  const res = await fetch(`${BASE}/api/analyses/${id}/feedback`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      ...(actualViews !== undefined ? { actual_views: actualViews } : {}),
      ...(actualLikes !== undefined ? { actual_likes: actualLikes } : {}),
    }),
  });
  return handleResponse<AnalysisOut>(res);
}

/**
 * Attach the user's posted TikTok link to an analysis and auto-fetch its real
 * view/like counts. Omit `url` to refresh counts from the already-stored link
 * (backend throttles refreshes to once per 24h). TikTok only.
 */
export async function linkTikTokVideo(
  id: string | number,
  url?: string
): Promise<AnalysisOut> {
  const res = await fetch(`${BASE}/api/analyses/${id}/video-link`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ url: url ?? null }),
  });
  return handleResponse<AnalysisOut>(res);
}

export interface ConsentStatus {
  seed_consent: "yes" | "no" | "ask";
  is_minor: boolean;
}

export async function getConsent(): Promise<ConsentStatus> {
  const res = await fetch(`${BASE}/api/me/consent`, {
    headers: authHeaders(),
  });
  return handleResponse<ConsentStatus>(res);
}

export async function updateConsent(
  seedConsent: "yes" | "no" | "ask"
): Promise<ConsentStatus> {
  const res = await fetch(`${BASE}/api/me/consent`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ seed_consent: seedConsent }),
  });
  return handleResponse<ConsentStatus>(res);
}

/** Answer the results-page seed consent banner. `remember` also saves the
 *  choice as the account-wide setting. */
export async function seedConsentDecision(
  id: string | number,
  allow: boolean,
  remember?: "yes" | "no"
): Promise<AnalysisOut> {
  const res = await fetch(`${BASE}/api/analyses/${id}/seed-consent`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ allow, ...(remember ? { remember } : {}) }),
  });
  return handleResponse<AnalysisOut>(res);
}

export async function verifyResetCode(token: string): Promise<{ valid: boolean }> {
  const res = await fetch(`${BASE}/api/auth/verify-reset-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  return handleResponse<{ valid: boolean }>(res);
}

export async function forgotPassword(email: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return handleResponse<{ ok: boolean }>(res);
}

export async function resetPassword(
  token: string,
  newPassword: string
): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  return handleResponse<{ ok: boolean }>(res);
}

export async function deleteAccount(password: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/me/account`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ password }),
  });
  return handleResponse<{ ok: boolean }>(res);
}

export async function changeUsername(
  newUsername: string,
  currentPassword: string
): Promise<{ username: string }> {
  const res = await fetch(`${BASE}/api/me/username`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ new_username: newUsername, current_password: currentPassword }),
  });
  return handleResponse<{ username: string }>(res);
}

export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/me/password`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  return handleResponse<{ ok: boolean }>(res);
}

export async function deleteAnalysis(
  id: number,
  token?: string | null
): Promise<void> {
  const res = await fetch(`${BASE}/api/analyses/${id}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${text}`);
  }
}

export async function getAdminSeeds(password: string): Promise<SeedVideoOut[]> {
  const res = await fetch(`${BASE}/api/admin/seeds`, {
    headers: { "X-Admin-Password": password },
  });
  return handleResponse<SeedVideoOut[]>(res);
}

export async function addSeedVideo(
  formData: FormData,
  password: string
): Promise<SeedVideoOut> {
  const res = await fetch(`${BASE}/api/admin/seed`, {
    method: "POST",
    headers: { "X-Admin-Password": password },
    body: formData,
  });
  return handleResponse<SeedVideoOut>(res);
}

export async function deleteSeedVideo(
  id: number,
  password: string
): Promise<void> {
  const res = await fetch(`${BASE}/api/admin/seeds/${id}`, {
    method: "DELETE",
    headers: { "X-Admin-Password": password },
  });
  await handleResponse<unknown>(res);
}

export interface FetchStatus {
  broken: boolean;
  message?: string;
  url?: string;
  when?: string;
}

export async function seedFromUrl(
  url: string,
  niche: string,
  password: string
): Promise<SeedVideoOut> {
  // Platform is auto-detected server-side from the URL domain.
  const form = new FormData();
  form.append("url", url);
  form.append("niche", niche);
  const res = await fetch(`${BASE}/api/admin/seed/from-url`, {
    method: "POST",
    headers: { "X-Admin-Password": password },
    body: form,
  });
  return handleResponse<SeedVideoOut>(res);
}

export async function getApiUsage(password: string): Promise<ApiUsage> {
  const res = await fetch(`${BASE}/api/admin/api-usage`, {
    headers: { "X-Admin-Password": password },
  });
  return handleResponse<ApiUsage>(res);
}

export async function getFetchStatus(password: string): Promise<FetchStatus> {
  const res = await fetch(`${BASE}/api/admin/fetch-status`, {
    headers: { "X-Admin-Password": password },
  });
  return handleResponse<FetchStatus>(res);
}

export async function ackFetchStatus(password: string): Promise<void> {
  const res = await fetch(`${BASE}/api/admin/fetch-status/ack`, {
    method: "POST",
    headers: { "X-Admin-Password": password },
  });
  await handleResponse<unknown>(res);
}

export interface SingleHarvestStatus {
  status: "never_run" | "running" | "done" | "failed" | "degraded";
  platform?: string;
  started_at?: string;
  finished_at?: string;
  niches_processed?: number;
  total_added?: number;
  total_skipped?: number;
  total_errors?: number;
  total_gemini_calls?: number;
  total_search_failures?: number;
  failed_niches?: number;
  // Granular skip breakdown
  total_skip_not_reel?: number;          // Instagram: search result was not a Reel
  total_skip_missing_id?: number;
  total_skip_missing_play_url?: number;  // TikTok: candidate had no playable URL
  total_skip_missing_url?: number;       // Instagram: candidate had no video URL
  total_skip_below_min_views?: number;   // TikTok: below min_views threshold
  total_skip_below_min_likes?: number;   // Instagram: below min_likes threshold
  total_skip_duplicate?: number;
  // Split error counters — separate stages for diagnosing zero results
  total_download_errors?: number;
  total_analysis_errors?: number;
  total_db_errors?: number;
  // Last error strings for each stage
  last_download_error?: string;
  last_analysis_error?: string;
  last_db_error?: string;
  error?: string;
  detail?: {
    niche: string;
    added: number;
    skipped: number;
    errors: number;
    search_failures?: number;
    gemini_calls?: number;
    skip_not_reel?: number;
    skip_missing_id?: number;
    skip_missing_play_url?: number;
    skip_missing_url?: number;
    skip_below_min_views?: number;
    skip_below_min_likes?: number;
    skip_duplicate?: number;
    download_errors?: number;
    analysis_errors?: number;
    db_errors?: number;
    last_download_error?: string;
    last_analysis_error?: string;
    last_db_error?: string;
  }[];
}

export interface HarvestStatus {
  tiktok?: SingleHarvestStatus;
  instagram?: SingleHarvestStatus;
}

export async function triggerHarvest(
  password: string,
  options?: { niches?: string[]; min_views?: number; max_views?: number; max_per_niche?: number; platform?: string; min_likes?: number }
): Promise<{ status: string; niches: number; platform: string }> {
  const res = await fetch(`${BASE}/api/admin/harvest`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Admin-Password": password },
    body: JSON.stringify(options ?? {}),
  });
  return handleResponse<{ status: string; niches: number; platform: string }>(res);
}

export interface RateLimitStatus {
  allowed: boolean;
  used: number;
  base_limit: number;
  bonus: number;
  effective_limit: number;
  remaining: number;
  resets_at: string | null;
  window_hours: number;
}

export async function getRateLimit(): Promise<RateLimitStatus> {
  const res = await fetch(`${BASE}/api/me/rate-limit`, {
    headers: authHeaders(),
  });
  return handleResponse<RateLimitStatus>(res);
}

export async function getPresignedUploadUrl(
  filename: string,
  contentType: string
): Promise<{ upload_url: string; key: string }> {
  const form = new FormData();
  form.append("filename", filename);
  form.append("content_type", contentType);
  const res = await fetch(`${BASE}/api/upload/presigned-url`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return handleResponse<{ upload_url: string; key: string }>(res);
}

export function uploadFileToR2(
  url: string,
  file: File,
  onProgress: (pct: number) => void,
  contentType: string = file.type || "video/mp4"
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`Upload failed: ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("Upload failed — check your connection and try again."));
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", contentType);
    xhr.send(file);
  });
}

export async function analyzeFromR2(
  r2Key: string,
  niche: string,
  caption: string = "",
  bio: string = "",
  platform: string = "tiktok",
  secondary: string = ""
): Promise<{ id: number; status: string }> {
  const form = new FormData();
  form.append("r2_key", r2Key);
  form.append("niche", niche);
  if (secondary) form.append("secondary", secondary);
  form.append("caption", caption);
  form.append("bio", bio);
  form.append("platform", platform);
  const res = await fetch(`${BASE}/api/analyze`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return handleResponse<{ id: number; status: string }>(res);
}

export async function getAnalysisStatus(
  id: number
): Promise<{ id: number; status: string }> {
  const res = await fetch(`${BASE}/api/analyses/${id}/status`);
  return handleResponse<{ id: number; status: string }>(res);
}

export async function getHarvestStatus(password: string): Promise<HarvestStatus> {
  const res = await fetch(`${BASE}/api/admin/harvest/status`, {
    headers: { "X-Admin-Password": password },
  });
  return handleResponse<HarvestStatus>(res);
}

export interface NicheInsightRow {
  niche: string;
  seed_count: number;
  generated_at: string;
  insight_preview: string;
}

export interface GenerateInsightsResult {
  platform: string;
  generated: number;
  total: number;
  results: { niche: string; status: "generated" | "skipped" | "error"; seed_count?: number; correction_count?: number; reason?: string }[];
}

export async function generateInsights(
  password: string,
  platform: string,
  niche?: string
): Promise<GenerateInsightsResult> {
  const form = new FormData();
  form.append("platform", platform);
  if (niche) form.append("niche", niche);
  const res = await fetch(`${BASE}/api/admin/insights/generate`, {
    method: "POST",
    headers: { "X-Admin-Password": password },
    body: form,
  });
  return handleResponse<GenerateInsightsResult>(res);
}

export async function getInsights(password: string, platform: string): Promise<NicheInsightRow[]> {
  const res = await fetch(`${BASE}/api/admin/insights?platform=${encodeURIComponent(platform)}`, {
    headers: { "X-Admin-Password": password },
  });
  return handleResponse<NicheInsightRow[]>(res);
}

// ── Trend Intelligence ────────────────────────────────────────────────────────

export interface TrendHarvestStatus {
  status: "never_run" | "running" | "done" | "failed";
  started_at?: string;
  finished_at?: string;
  niches_processed?: number;
  total_added?: number;
  total_skipped?: number;
  total_errors?: number;
  total_gemini_calls?: number;
  total_search_failures?: number;
  failed_niches?: number;
  error?: string;
}

export interface TrendRow {
  niche: string;
  recent_seed_count: number;
  established_seed_count: number;
  generated_at: string;
  trend_preview: string;
}

export interface GenerateTrendsResult {
  platform: string;
  generated: number;
  total: number;
  results: { niche: string; status: "generated" | "skipped" | "error"; recent_count?: number; reason?: string }[];
}

export async function triggerTrendHarvest(
  password: string,
  options?: { max_age_days?: number; min_velocity?: number; max_per_niche?: number }
): Promise<{ status: string; niches: number }> {
  const res = await fetch(`${BASE}/api/admin/trends/harvest`, {
    method: "POST",
    headers: { "X-Admin-Password": password, "Content-Type": "application/json" },
    body: JSON.stringify(options ?? {}),
  });
  return handleResponse(res);
}

export async function getTrendHarvestStatus(password: string): Promise<TrendHarvestStatus> {
  const res = await fetch(`${BASE}/api/admin/trends/harvest/status`, {
    headers: { "X-Admin-Password": password },
  });
  return handleResponse<TrendHarvestStatus>(res);
}

export async function generateTrends(
  password: string,
  platform: string,
  niche?: string
): Promise<GenerateTrendsResult> {
  const form = new FormData();
  form.append("platform", platform);
  if (niche) form.append("niche", niche);
  const res = await fetch(`${BASE}/api/admin/trends/generate`, {
    method: "POST",
    headers: { "X-Admin-Password": password },
    body: form,
  });
  return handleResponse<GenerateTrendsResult>(res);
}

export async function getTrends(password: string, platform: string): Promise<TrendRow[]> {
  const res = await fetch(`${BASE}/api/admin/trends?platform=${encodeURIComponent(platform)}`, {
    headers: { "X-Admin-Password": password },
  });
  return handleResponse<TrendRow[]>(res);
}
