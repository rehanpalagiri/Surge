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
    hook_strength: number;
    pacing_score: number;
    audio_score: number;
    caption_score: number;
    trend_alignment: number;
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
    locked?: boolean;
    error?: string;
  };
  verdict: string;
  actual_views: number | null;
  actual_likes: number | null;
  video_url?: string | null;          // posted TikTok link (counts auto-fetched)
  counts_fetched_at?: string | null;
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
  created_at: string;
}

export interface ImprovementItem {
  area: string;
  priority: number;
  current_score: number;
  problem: string;
  fix: string;
  example: string;
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
  return msg || fallback;
}

/**
 * Render's free tier spins the backend down after ~15 min idle, so the very
 * first request after a lull can take 20-60s to wake it up. If that wake-up
 * happens *during* the big multipart video upload, mobile Safari tends to
 * drop the connection entirely and throw a generic "Load failed" — instead,
 * ping the lightweight /health endpoint first (small, cheap requests) and
 * keep retrying until the backend responds, THEN kick off the real upload
 * once it's already warm. Returns true once the backend answers, or false if
 * it never wakes within maxWaitMs (caller can still try the real request).
 */
export async function wakeBackend(maxWaitMs: number = 90_000): Promise<boolean> {
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
  file: File,
  niche: string,
  caption: string = "",
  bio: string = "",
  platform: string = "tiktok",
  mode: string = "quick"
): Promise<{ id: number }> {
  const form = new FormData();
  form.append("file", file);
  form.append("niche", niche);
  form.append("caption", caption);
  form.append("bio", bio);
  form.append("platform", platform);
  form.append("mode", mode);
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
  username: string,
  password: string
): Promise<TokenOut> {
  const res = await fetch(`${BASE}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
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
  actualViews: number,
  actualLikes?: number
): Promise<AnalysisOut> {
  const res = await fetch(`${BASE}/api/analyses/${id}/feedback`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      actual_views: actualViews,
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
