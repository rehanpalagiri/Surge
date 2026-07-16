import { getToken } from "./auth";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const CLAIM_TOKEN_PREFIX = "surge_claim_token:";

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
  project_name?: string | null;
  niche: string;
  caption: string | null;
  bio: string | null;
  scores_json: {
    overall_score?: number; // legacy analyses only; never shown as a performance metric
    hook_velocity: number;
    // cut_frequency / text_scannability may be null when the review marked the
    // dimension not applicable (deliberate format choice, e.g. one-take video).
    cut_frequency: number | null;
    text_scannability: number | null;
    curiosity_gap: number;
    audio_visual_sync: number;
    loop_seamlessness: number;
    // dimension key → ≤12-word reason ("one-take format — the shot is the format")
    not_applicable?: Record<string, string>;
    strengths: string[];
    improvements: string[];
    verdict: string;
    analysis_summary: string;
    improvement_plan?: ImprovementItem[];
    caption_rewrite?: string;
    hook_rewrite?: string;
    attention_risk_map?: AttentionRiskItem[];
    rubric_context?: RubricContext;
    first_improvement?: ImprovementItem | null;
    emotional_analysis?: EmotionalAnalysis;
    recommended_experiment?: RecommendedExperiment;
    craft_review_version?: number;
    evidence_notice?: string;
    niche_harvest_used?: boolean;
    locked?: boolean;
    error?: string;
  };
  verdict: string;
  actual_views: number | null;
  actual_likes: number | null;
  video_url?: string | null;          // posted TikTok link (counts auto-fetched)
  counts_fetched_at?: string | null;
  claim_token?: string | null;        // initial anonymous response only
  pending_seed_consent?: boolean;     // owner's consent is "ask" — show the banner
  mode?: string;
  parent_id?: number | null;          // ID of the analysis this updates
  created_at: string;
}

function browserStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function rememberAnalysisClaimToken(id: string | number, token?: string | null) {
  if (!token) return;
  browserStorage()?.setItem(`${CLAIM_TOKEN_PREFIX}${id}`, token);
}

export function analysisClaimToken(id: string | number): string | null {
  return browserStorage()?.getItem(`${CLAIM_TOKEN_PREFIX}${id}`) ?? null;
}

export function forgetAnalysisClaimToken(id: string | number) {
  browserStorage()?.removeItem(`${CLAIM_TOKEN_PREFIX}${id}`);
}

export interface AnalysisSummary {
  id: number;
  platform: string;
  project_name?: string | null;
  niche: string;
  verdict: string;
  caption_preview: string | null;
  actual_views: number | null;
  actual_likes: number | null;
  video_url?: string | null;
  counts_fetched_at?: string | null;
  mode?: string;
  parent_id?: number | null;
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
  email_verified?: boolean;
  created_at: string;
}

export interface EmotionalAnalysis {
  target_emotions: string[];      // the feeling(s) the video should evoke
  achieved_score: number | null;  // 0-10 when assessed; null when Gemini did not assess it
  assessed?: boolean;             // absent on legacy analyses; numeric scores still count as assessed
  what_lands?: string;            // what makes the feeling work ("" if it doesn't land)
  what_misses?: string;           // what blunts the feeling ("" if it lands fully)
  how_to_amplify?: string[];      // concrete changes to deepen the feeling
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

export interface RecommendedExperiment {
  change: string;
  keep_constant: string;
  observe: string;
}

export interface AttentionRiskItem {
  section: string;
  risk: "low" | "medium" | "high";
  reason: string;
  fix?: string;
}

export interface RubricContext {
  source?: "auto_detected" | "user_hint" | "fallback" | string;
  primary_niche?: string | null;
  secondary_niche?: string | null;
  reviewed_primary_niche?: string | null;
  reviewed_secondary_niche?: string | null;
  format?: string;
  intent?: string;
  confidence?: "high" | "medium" | "low" | string;
  evidence?: string[];
}

export interface OutcomeSnapshot {
  id: number;
  analysis_id: number;
  platform: string;
  source: string;
  observed_at: string;
  posted_at?: string | null;
  post_age_hours?: number | null;
  horizon?: "24h" | "7d" | "30d" | null;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  shares?: number | null;
  saves?: number | null;
  creator_followers?: number | null;
  metric_version: string;
  integrity_flags_json?: string | null;
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
  secondary: string = "",
  projectName: string = ""
): Promise<{ id: number; claim_token?: string | null }> {
  const form = new FormData();
  if (file) form.append("file", file);
  if (videoUrl) form.append("video_url", videoUrl);
  form.append("niche", niche);
  if (secondary) form.append("secondary", secondary);
  form.append("caption", caption);
  form.append("bio", bio);
  form.append("platform", platform);
  form.append("project_name", projectName);
  const res = await fetch(`${BASE}/api/analyze`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return handleResponse<AnalysisOut>(res).then((a) => {
    rememberAnalysisClaimToken(a.id, a.claim_token);
    return { id: a.id, claim_token: a.claim_token };
  });
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

export async function googleAuth(credential: string, birthDate?: string | null): Promise<TokenOut> {
  const res = await fetch(`${BASE}/api/auth/google`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential, birth_date: birthDate ?? null }),
  });
  return handleResponse<TokenOut>(res);
}

export async function getMe(token?: string | null): Promise<UserOut> {
  const res = await fetch(`${BASE}/api/auth/me`, {
    headers: authHeaders(token),
  });
  return handleResponse<UserOut>(res);
}

export async function verifyEmail(code: string, token?: string | null): Promise<UserOut> {
  const res = await fetch(`${BASE}/api/auth/verify-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ code }),
  });
  return handleResponse<UserOut>(res);
}

export async function resendVerification(token?: string | null): Promise<void> {
  const res = await fetch(`${BASE}/api/auth/resend-verification`, {
    method: "POST",
    headers: authHeaders(token),
  });
  await handleResponse(res);
}

export async function getMyAnalyses(
  token?: string | null
): Promise<AnalysisSummary[]> {
  const res = await fetch(`${BASE}/api/me/analyses`, {
    headers: authHeaders(token),
  });
  return handleResponse<AnalysisSummary[]>(res);
}

export async function getOutcomeSnapshots(
  id: string | number,
  token?: string | null,
): Promise<OutcomeSnapshot[]> {
  const res = await fetch(`${BASE}/api/analyses/${id}/outcomes`, {
    headers: authHeaders(token),
  });
  return handleResponse<OutcomeSnapshot[]>(res);
}

export async function claimAnalysis(
  id: string | number,
  token?: string | null,
  claimToken: string | null = analysisClaimToken(id)
): Promise<AnalysisOut> {
  const res = await fetch(`${BASE}/api/analyses/${id}/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ claim_token: claimToken }),
  });
  return handleResponse<AnalysisOut>(res).then((a) => {
    forgetAnalysisClaimToken(id);
    return a;
  });
}

export async function submitFeedback(
  id: string | number,
  actualViews: number | undefined,
  actualLikes?: number,
  postAgeHours?: number,
  videoUrl?: string
): Promise<AnalysisOut> {
  const res = await fetch(`${BASE}/api/analyses/${id}/feedback`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      ...(actualViews !== undefined ? { actual_views: actualViews } : {}),
      ...(actualLikes !== undefined ? { actual_likes: actualLikes } : {}),
      ...(postAgeHours !== undefined ? { post_age_hours: postAgeHours } : {}),
      ...(videoUrl ? { video_url: videoUrl } : {}),
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
  url?: string,
  postAgeHours?: number
): Promise<AnalysisOut> {
  const res = await fetch(`${BASE}/api/analyses/${id}/video-link`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      url: url ?? null,
      post_age_hours: postAgeHours ?? null,
    }),
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

export async function verifyResetCode(token: string, email?: string): Promise<{ valid: boolean }> {
  const res = await fetch(`${BASE}/api/auth/verify-reset-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, email }),
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
  newPassword: string,
  email?: string
): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword, email }),
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
): Promise<{ ok: boolean; access_token?: string }> {
  const res = await fetch(`${BASE}/api/me/password`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  return handleResponse<{ ok: boolean; access_token?: string }>(res);
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

export interface UserSeedRow {
  id: number;
  platform: string;
  niche: string;
  canonical_niche: string | null;
  project_name: string | null;
  verdict: string;
  dimensions: Partial<Record<
    "hook_velocity" | "cut_frequency" | "text_scannability" |
    "curiosity_gap" | "audio_visual_sync" | "loop_seamlessness",
    number
  >>;
  actual_views: number | null;
  actual_likes: number | null;
  counts_fetched_at: string | null;
  in_seed_pool: boolean;   // promoted into the shared seed pool (has verified counts)
  video_url: string | null;
  created_at: string | null;
}

export async function getUserSeeds(password: string): Promise<UserSeedRow[]> {
  const res = await fetch(`${BASE}/api/admin/user-seeds`, {
    headers: { "X-Admin-Password": password },
  });
  return handleResponse<UserSeedRow[]>(res);
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
  tier: "free" | "pro";
  unlimited: boolean;
  used: number;
  base_limit: number | null;
  bonus: number;
  effective_limit: number | null;
  remaining: number | null;
  resets_at: string | null;
  period: "month";
}

export async function getRateLimit(): Promise<RateLimitStatus> {
  const res = await fetch(`${BASE}/api/me/rate-limit`, {
    headers: authHeaders(),
  });
  return handleResponse<RateLimitStatus>(res);
}

// ── Billing (CraftLint Pro) ────────────────────────────────────────────────────
export interface BillingStatus {
  plan: "free" | "pro";
  is_pro: boolean;
  comp: boolean;
  subscription_status: string | null;
  current_period_end: string | null;
  has_customer: boolean;
  price: string;
  configured: boolean;
}

export async function getBillingStatus(): Promise<BillingStatus> {
  const res = await fetch(`${BASE}/api/billing/status`, { headers: authHeaders() });
  return handleResponse<BillingStatus>(res);
}

/** Start a CraftLint Pro subscription — returns the Stripe hosted-checkout URL. */
export async function createCheckoutSession(): Promise<{ url: string }> {
  const res = await fetch(`${BASE}/api/billing/checkout`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<{ url: string }>(res);
}

/** Open the Stripe billing portal to manage/cancel — returns its URL. */
export async function createPortalSession(): Promise<{ url: string }> {
  const res = await fetch(`${BASE}/api/billing/portal`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<{ url: string }>(res);
}

export interface CraftInsightPost {
  analysis_id: number;
  project_name: string | null;
  niche: string;
  created_at: string | null;
  // A dimension is null when the review marked it not applicable.
  scores: Record<string, number | null>;
  views: number;
  likes: number;
  like_rate: number; // observed likes/views, percent
}

export interface CraftPattern {
  dimension: string;
  label: string;
  n_high: number;
  n_low: number;
  median_like_rate_high: number;
  median_like_rate_low: number;
  delta: number;
  direction: "higher" | "lower" | "flat";
}

export interface CraftInsightPending {
  analysis_id: number;
  project_name: string | null;
  platform: string;
  // instagram_no_views: provider never returns view counts — permanent, not a wait.
  // low_views: has a checked-in snapshot but it's under the reliable-rate view floor.
  // awaiting_checkpoint: linked, waiting on its next 24h/7d/30d collection job.
  reason: "instagram_no_views" | "low_views" | "awaiting_checkpoint";
  eta: string | null; // ISO timestamp of the next collection job's due date, if any
  eta_horizon: "24h" | "7d" | "30d" | null;
  overdue?: boolean; // true if eta has passed and the daily collector hasn't run yet
}

export interface CraftInsights {
  total_analyses: number;
  with_verified_outcome: number;
  horizon: "24h" | "7d" | "30d" | null;
  metric: "observed_like_rate";
  posts: CraftInsightPost[];
  patterns: CraftPattern[];
  pattern_min: number;
  observed_range:
    | {
        available: false;
        need: number;
        have: number;
        // Present when 1 ≤ have < need: plain descriptive stats of the
        // creator's own like rates (median/min/max only — never a band).
        preliminary?: { n: number; horizon: string; median: number; min: number; max: number };
      }
    | { available: true; n: number; horizon: string; p25: number; median: number; p75: number; min: number; max: number };
  pending: CraftInsightPending[];
  notice: string;
}

export async function getCraftInsights(): Promise<CraftInsights> {
  const res = await fetch(`${BASE}/api/me/craft-insights`, {
    headers: authHeaders(),
  });
  return handleResponse<CraftInsights>(res);
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
  secondary: string = "",
  parentId?: number,
  projectName: string = ""
): Promise<{ id: number; status: string; claim_token?: string | null }> {
  const form = new FormData();
  form.append("r2_key", r2Key);
  form.append("niche", niche);
  if (secondary) form.append("secondary", secondary);
  form.append("caption", caption);
  form.append("bio", bio);
  form.append("platform", platform);
  form.append("project_name", projectName);
  if (parentId != null) form.append("parent_id", String(parentId));
  const res = await fetch(`${BASE}/api/analyze`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return handleResponse<{ id: number; status: string; claim_token?: string | null }>(res).then((a) => {
    rememberAnalysisClaimToken(a.id, a.claim_token);
    return a;
  });
}

export async function getAnalysisStatus(
  id: number,
  token?: string | null
): Promise<{ id: number; status: string; message?: string }> {
  // Send auth when we have it: the status endpoint now returns 404 to non-owners
  // of a claimed analysis, so an authenticated owner must identify themselves.
  // Guests (no token) can still poll their own not-yet-claimed upload.
  const res = await fetch(`${BASE}/api/analyses/${id}/status`, { headers: authHeaders(token) });
  return handleResponse<{ id: number; status: string; message?: string }>(res);
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
