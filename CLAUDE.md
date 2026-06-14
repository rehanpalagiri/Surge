# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

### Backend (FastAPI)
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```
The venv is at `backend/venv/`. Backend reads `backend/.env` automatically via `python-dotenv`. Never run `pip install` outside the venv.

### Frontend (Next.js 15)
```bash
cd frontend
npm run dev       # :3000
npm run build     # production build — run before deploying to catch type errors
npm run lint
```
`frontend/.env.local` must contain `NEXT_PUBLIC_API_URL=http://localhost:8000` for local dev.

---

## Architecture

### Request flow
```
Browser → Next.js (Vercel) → FastAPI (Render) → Neon Postgres
                                              → Google Gemini 2.5 Flash (video analysis)
```

### Backend — six tables, six routers

**Models (`models.py`):**
- `users` — username (display name) + bcrypt password hash. v1.24: `email` (unique, primary login identifier; nullable for pre-1.24 accounts), `birth_year` (age gate: 13+ to sign up), `seed_consent` (`"yes" | "no" | "ask"` — minors 13–17 are forced to `"no"` permanently; adults default `"ask"`).
- `user_profiles` — one row per (user, platform). Stores `handle`, `display_name`, `bio`, `target_audience`, `niche`. Unique constraint on `(user_id, platform)`. Platform is `"tiktok"` or `"instagram"`.
- `seed_videos` — reference TikTok/Instagram videos with `view_count`, `like_count`, `niche`, `posted_at` (original post date), `rating` (0–10 virality from Gemini seed analysis), `gemini_analysis` (full JSON writeup — the durable artifact; the video file is deleted after analysis). `performed` is a **deprecated vestigial column** (kept `nullable, default=False` so SQLAlchemy satisfies the old prod `NOT NULL` constraint on insert — do not read it).
- `user_analyses` — every analysis run. `user_id` nullable (anonymous). Has `platform` column (default `"tiktok"`), `mode` (the **effective** mode that ran: `"quick" | "thinking" | "deep_thinking"`), and `pending_seed_consent` (v1.24 — verified link arrived while the owner's `seed_consent` was `"ask"`; the results page shows the consent banner).
- `password_reset_tokens` — v1.25. `user_id`, `token` (6-digit code as string, unique+indexed), `expires_at` (1h TTL), `used` bool. Created by `create_all` — no shim needed. Old unused tokens for a user are invalidated when a new one is issued.
- `fetch_status` — log of yt-dlp auto-fetch attempts (success/fail)

**Key files:**
- **`main.py`** — FastAPI app, CORS, lifespan. Runs `Base.metadata.create_all` then `_ensure_columns` (SQLite-only migration shim). Registers all routers.
- **`database.py`** — Async SQLAlchemy engine. SQLite locally (no config), Neon Postgres in prod. asyncpg requires: scheme normalisation, stripping `?sslmode=` from URL, SSL via `certifi` CA bundle in `connect_args`, `statement_cache_size=0` for pooler.
- **`auth.py`** — `bcrypt` (direct, no passlib — passlib 4.x was incompatible), `PyJWT` 30-day tokens. Two deps: `require_user` (401) and `optional_user` (returns `None`).
- **`routers/auth.py`** (v1.26) — signup requires `email` + `username` + `password` (min 8) + `birth_year` (under-13 → 403; 13–17 → `seed_consent="no"` locked; 18+ → `"ask"`). Login accepts **email OR username** in the same field. **Password reset (v1.25):** `POST /api/auth/forgot-password` generates a 6-digit code (`secrets.randbelow(1_000_000)` zero-padded), stores it in `password_reset_tokens`, and fires `_send_reset_email` via FastAPI `BackgroundTasks` (response returns before email sends). `POST /api/auth/verify-reset-code` checks the token is valid+unexpired without consuming it — the frontend uses this to gate the password fields. `POST /api/auth/reset-password` validates + updates `password_hash`. Email uses **Brevo SMTP** via `aiosmtplib` with `certifi.where()` as `cert_bundle` (critical — without certifi the SSL handshake silently fails on Render). `_send_reset_email` logs failures via `logger.error` but never raises (email failure must never break the HTTP response).
- **`routers/analyze.py`** — `POST /api/analyze` (optional auth; `platform` + `mode` form fields, `ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime"}`). **Gemini quota guard (v1.26):** catches `google.genai.errors.ClientError` with `code in (429, 403)` *before* creating the `UserAnalysis` row — returns 503, no broken row stored, no rate credit consumed. **Three-mode engine:** `resolve_mode()` computes the *effective* mode server-side and degrades gracefully (guests→Quick; Deep without a channel profile→Thinking; Thinking/Deep without usable seed buckets→Quick) so the results badge can never overclaim. Quick = raw video + caption only; Thinking adds the global seed reference + `profile_context`; Deep adds the creator channel profile. `PATCH /api/analyses/{id}/feedback` enforces hard sanity blocks (views ≥0, likes ≥0, likes ≤ views for TikTok, views ≤ 500M). `POST /api/analyses/{id}/video-link` (v1.19, TikTok only) attaches the user's posted video URL and auto-fetches real views/likes via `tiktok_fetch`; `url=None` refreshes from the stored link (24h cooldown → 429). Soft ownership check: 422 if the saved profile handle and the video's author handle both exist and differ. **On a successful link (v1.20) it schedules a background task (`services.seed_promote`) that auto-promotes the verified video into the seed library** — idempotent via `user_analyses.promoted_seed_id`. `GET /api/analyses/{id}` returns `_to_locked()` (verdict + predicted_views only) for anonymous or `_to_out()` for auth. `POST /api/analyses/{id}/claim` transfers anon analysis to account. **Rate limit (v1.23):** `services/rate_limit.py` — auth'd users get 10 uploads per rolling 3h window + 1 bonus credit per all-time verified link (capped +10, so max 20/3h); over-limit → 429; guests unmetered. `GET /api/me/rate-limit` feeds the UploadZone status bar. **Seed consent (v1.24):** `POST /api/analyses/{id}/seed-consent` (`{allow, remember?}`) answers the results-page banner — `allow=true` re-runs `promote_analysis_to_seed` with `consent_override=True`; `remember` persists the choice account-wide (minors hard-blocked). **Personalized calibration (v1.28):** on every Instagram analysis, queries `UserAnalysis.actual_likes` for the current user (last 10 rows, same platform) — if ≥2 data points exist, passes `creator_like_baseline` dict (`median_likes`, `sample_count`, `min_likes`, `max_likes`) to `analyze_video()` so the Gemini prompt anchors the 1–10 scale to the creator's own typical performance rather than generic industry thresholds.
- **`services/channel_profile.py`** — `build_channel_profile(analyses)`: pure, unit-testable function over already-fetched `UserAnalysis` rows. Returns a prompt block (or `None` if <2 analyses). Two tiers: **A. Verified performance** (real `actual_views` rows — the prediction anchor) and **B. Self-assessment trends** (derived from past `scores_json`, framed explicitly as the system's own prior opinion). `recent_history` excludes past `predicted_views` to avoid the AI anchoring on its own guesses.
- **`services/seed_analysis.py`** — `analyze_seed_video()`: runs an AI-consumption-only seed-analysis prompt on an uploaded reference video, returns JSON with `virality_rating` + `seed_summary`. Reuses the `client`/`_PLATFORM_CONTEXT`/upload-poll-generate-delete pattern from `gemini.py`. Admin rejects (no row) on bad JSON or missing rating.
- **`services/niche_classifier.py`** — `classify_niche(raw)`: maps the user's free-text niche to one of `CANONICAL_NICHES` (50 labels since v1.22) via a small text-only Gemini call. Exact case-insensitive matches skip the API call; any failure/timeout (10s) falls back to `"Lifestyle & Vlogs"` — classification can never block an analysis. The canonical label drives seed matching (`select_seed_examples` is an exact string compare); the raw text is stored on `user_analyses.niche` and passed to the prompt as `niche_raw` for specificity. **The admin seed form's `NICHES` list (`frontend/app/admin/page.tsx`) must stay in sync with `CANONICAL_NICHES`.**
- **`routers/profile.py`** — `GET /api/me/profile/{platform}` and `PUT /api/me/profile/{platform}` (upsert). Requires auth.
- **`routers/settings.py`** — `PATCH /api/me/username` and `PATCH /api/me/password`. Both require `current_password` in the request body for verification before applying the change. v1.24: `GET /api/me/consent` (minors always read `"no"`) and `PATCH /api/me/consent` (403 for minors; values `yes|no|ask`). v1.29: `DELETE /api/me/account` — GDPR account deletion, requires `password` in body. Deletes in FK order: `PasswordResetToken` → `UserProfile` → nullify `UserAnalysis.user_id` (keeps anonymised rows) → delete `User`. Returns `{"ok": True}`.
- **`routers/admin.py`** — `X-Admin-Password` header auth. Seed CRUD + `POST /api/admin/seed/from-url` (tikwm.com for TikTok — free/keyless, works from any IP; EaseApi on RapidAPI for Instagram — 20 req/month free cap). Both upload paths run `analyze_seed_video` synchronously via `_analyze_and_persist_seed` (analyze → store `rating` + `gemini_analysis` → delete the file); a seed with no usable rating is **never** persisted (502, retry). v1.22 ("Door A"): `POST /api/admin/harvest` (BackgroundTask) + `GET /api/admin/harvest/status`. v1.29: `HarvestRequest` has a `platform` field (`"tiktok"` | `"instagram"`) — Instagram dispatch calls `harvest_instagram_all`; TikTok calls `harvest_all`. Status endpoint returns `{"tiktok": ..., "instagram": ...}`.
- **`services/seed_harvest.py`** (v1.22, "Door A") — automated TikTok seed harvesting: `NICHE_KEYWORDS` maps all 50 canonical niches to 3–4 tikwm search keywords (**must stay in lockstep with `CANONICAL_NICHES`**). Per niche: `GET tikwm /api/feed/search` → filter `play_count ≥ min_views` (default 500K) → dedupe via `vid:{video_id}` tag in `notes` → download the short-lived `play` URL → `analyze_seed_video` → persist with `source="harvest"`. ~1.2s sleep between searches (tikwm ~1 req/sec). Triggered from the admin page button or the weekly GitHub Actions cron (`.github/workflows/harvest.yml`, Mondays 06:00 UTC, needs `ADMIN_PASSWORD` repo secret).
- **`services/instagram_harvest.py`** (v1.29) — automated Instagram seed harvesting via **HikerAPI** (`api.hikerapi.com`, `x-access-key` header, `HIKERAPI_KEY` env var). **Free tier: 100 requests/month.** Budget: `_IG_KEYWORDS_PER_NICHE = 2` (first 2 keywords per niche from `NICHE_KEYWORDS`) × 50 niches = 100 calls exactly. `_IG_RESULTS_PER_CALL = 50` → up to 5,000 reel candidates per run. `_IG_CONCURRENCY = 3` niches processed in parallel via `asyncio.Semaphore` + `asyncio.gather`. Endpoint: `GET /v1/hashtag/medias/top?name={hashtag}&amount=50`. Filters for `media_type == 2` AND `product_type == "clips"` (Reels only). Dedupes via `ig:{media_pk}` in `notes`. Persists `view_count=None` (Instagram hides views), `like_count` as primary engagement. Entry points: `harvest_instagram_all()`, `harvest_instagram_niche()`, `get_last_instagram_harvest()`.
- **`services/tiktok_fetch.py`** — `fetch_tiktok(url)`: public TikTok metadata via tikwm.com (views, likes, caption, posted_at, author_handle). Raises `ValueError` on failure. Shared by the admin seed fetcher and the user video-link endpoint. `is_tiktok_url()` validates links.
- **`services/seed_promote.py`** (v1.20, "Door B") — `promote_analysis_to_seed(analysis_id)`: background task fired after a verified user video-link. Re-fetches the video (tikwm), classifies the niche to canonical, downloads + runs `analyze_seed_video`, and persists a `SeedVideo` with `source="user"` — real verified counts make these the *best* seed signal. Idempotent (`user_analyses.promoted_seed_id`), self-contained DB session (request session is closed by then), every failure logged + swallowed (promotion never breaks the user's stat-sync). Only the **verified link** path promotes — manual feedback entry never does (un-verifiable). **Consent gate (v1.24):** before the heavy phase it loads the owner — minors never promote; `seed_consent="no"` → skip; `"ask"` → sets `pending_seed_consent=True` and parks (the results-page banner + `/seed-consent` endpoint resume with `consent_override=True`); `"yes"` → proceeds.
- **`services/gemini.py`** — Uploads video to Gemini Files API, polls until `ACTIVE`, calls `gemini-2.5-flash` with `response_mime_type="application/json"`. **Exception handling:** the `google-genai` 1.x SDK does NOT depend on `google-api-core` — quota/key errors are `google.genai.errors.ClientError` (not `google.api_core.exceptions`). Quota (429) and bad-key (403) are re-raised so the router can catch them before writing to DB. Key behaviours:
  1. **`select_seed_examples()`** — buckets seeds into HIGH (`rating ≥ 6`) / LOW (`rating ≤ 4`) by Gemini virality rating (disjoint, so no overlap; rating 5/None is dormant). The HIGH/LOW label is derived in code from the rating, never written by the model. Recency (`view_count × exp(-age_days/60)`) is only an intra-rating tiebreaker.
  2. **`_build_system_prompt(..., mode, creator_like_baseline)`** — assembles the prompt per effective mode: Quick (no reference), Thinking (+ seed buckets + numeric benchmark), Deep (+ channel profile). Mode-specific predicted-views/likes guidance. **v1.28:** when `creator_like_baseline` has ≥2 verified posts, inserts a personalized calibration block anchoring score 5 = creator's `median_likes`, score 7 = 2–3× their typical, score 9 = 8× their typical. Falls back to generic industry thresholds if <2 data points.
  3. **Platform-aware (v1.27)** — `is_instagram` flag drives separate JSON schema per platform. Instagram outputs `predicted_likes` as the primary field (no `predicted_views` / `projected_views`). TikTok outputs `predicted_views` as before. `_PLATFORM_CONTEXT` dict has separate algorithm descriptions, key signals, and tips for TikTok vs Instagram (shared with `seed_analysis.py`).

### Frontend

**App Router** (Next.js 15). Any page using `useParams()`, `useSearchParams()`, or auth state must be `"use client"`. Server components cannot use these hooks and `params` is a Promise in server components.

**Key files:**
- **`app/page.tsx`** — `"use client"`. Platform switcher (TikTok / Instagram). `PLATFORM_CONFIG` drives all platform-specific visuals: `pageBg`, `badgeClass`, `accentClass`, `statColors`, `btnGradient`, etc. TikTok tab uses near-black bg + glitch text-shadow; Instagram uses purple-orange gradient.
- **`app/settings/page.tsx`** — Change username, change password, and (v1.24) the "Data & Privacy" seed-consent card: minors see a static exclusion note; adults get yes/ask/no radios (optimistic update, reverts on failure). v1.29: `DeleteAccountCard` — two-step confirm flow (idle → password input → loading → done). Calls `deleteAccount(password)` then `clearToken()` and redirects to `/`. Footer links to /privacy and /terms. (Light mode was removed in v1.18 — the app is dark-only.)
- **`app/privacy/page.tsx` + `app/terms/page.tsx`** (v1.24) — static server-rendered legal pages. Privacy has the `#seed-pool` anchor the consent UIs link to; effective dates are hardcoded — update them when the policy materially changes. Contact: surgeprivacy@gmail.com. Home page footer links to both.
- **`app/signup/page.tsx`** — email (required) + username + password (min 8) + birth year + required ToS/Privacy checkbox. Inline under-13 error as soon as a 4-digit year is typed; server errors surfaced via `apiErrorDetail`. Login accepts username or email in one field.
- **`app/forgot-password/page.tsx`** (v1.25) — 4-step password reset: (1) email entry, (2) OTP input (6 individual digit boxes in XXX·XXX layout, auto-advance, backspace-back, paste), (3) password fields — shown only after `verifyResetCode()` succeeds, (4) success. "Resend code" returns to step 1.
- **`app/results/[id]/page.tsx`** — `SeedConsentBanner`: dismissible card shown when `analysis.pending_seed_consent` (owner's setting is "ask"). Buttons: Yes / No thanks / Always yes / Always no — any click dismisses immediately and fires `seedConsentDecision` best-effort.
- **`app/admin/page.tsx`** — Admin seed panel. v1.29: TikTok/Instagram platform toggle; shows "Min views" (TikTok) or "Min likes" (Instagram) input. Harvest status split into per-platform blocks using `harvestStatus?.tiktok` and `harvestStatus?.instagram` from the `{tiktok: ..., instagram: ...}` response shape.
- **`app/onboarding/page.tsx`** — Two-step profile setup after signup (TikTok → Instagram). Skippable.
- **`app/profile/page.tsx`** — Tabbed TikTok/Instagram profile editor.
- **`components/UploadZone.tsx`** — Accepts `platform` prop. Auto-fills bio from saved profile on platform change. Calls `wakeBackend()` before submitting to avoid cold-start "Load failed" on mobile. **Niche is free text** (max 80 chars, required — client blocks submit and server 400s on empty) with quick-tap suggestion chips; the backend classifies it to a canonical niche. Logged-in users get a **Quick / Thinking / Deep** depth selector (remembered in `localStorage` key `surge_mode`); guests see an inline "sign in for Thinking & Deep" link and always send `quick`. Passes `platform` + `mode` to `analyzeVideo()`. The results page shows a badge of the *effective* mode (`analysis.mode`).
- **`components/Nav.tsx`** — Hamburger menu on mobile (animated 3-bar → ✕ toggle, dropdown); full horizontal layout on desktop (`md+`). Listens to `surge-auth` + `storage` events. Auth links: My Projects, Profile, Settings, Log out. Carries the version badge (e.g. `v1.18`) — bump it on each release.
- **`lib/auth.ts`** — Token in `localStorage` as `surge_token` (auto-migrates from old `viraliq_token`). `setToken`/`clearToken` dispatch `surge-auth` CustomEvent.
- **`lib/api.ts`** — All API calls. `wakeBackend()` pings `/health` in a retry loop (up to 90s) before the heavy video upload to avoid mobile Safari "Load failed" errors on Render cold starts. `changeUsername` / `changePassword` / `deleteAccount` call the settings endpoints. v1.29: `HarvestStatus` is `{tiktok?: SingleHarvestStatus, instagram?: SingleHarvestStatus}`; `triggerHarvest` accepts `platform?` and `min_likes?` options.
- **`components/UpsellModal.tsx`** — Shown to anonymous users on locked results.
- **`components/VerdictBanner.tsx`** — Verdict + predicted stats. v1.27: Instagram branch shows only `predictedLikes` (no views row at all — Instagram hides view counts). TikTok branch unchanged (`predictedViews` + `predictedLikes`).
- **`components/FeedbackModal.tsx`** — Actual-performance entry on the results page. TikTok: link-first — paste the posted video URL → `POST /api/analyses/{id}/video-link` auto-fetches real stats (manual entry remains as a toggle). Instagram: manual likes via `PATCH /api/analyses/{id}/feedback`. My Projects cards (TikTok) also carry a link/refresh affordance per card.
- **`app/results/[id]/improve/page.tsx`** — v1.27: `hasProjection` uses `projected_likes` for Instagram (`isInstagram ? s.projected_likes : s.projected_views`). Hides `projected_views` row entirely for Instagram.

**Freemium gate:** `results/[id]/page.tsx` checks `scores_json.locked`. Locked data is stripped server-side in `_to_locked()` — full scores never leave the backend for anonymous users.

**Claim flow:** After signup/login, if `?next=/results/{id}` is present, calls `claimAnalysis(id)` to transfer the anonymous analysis to the new account.

### Theme / colour system

The app is **dark-only** (light mode was removed in v1.18). All colours are CSS variables defined on `:root` in `globals.css`.

`tailwind.config.ts` maps every colour token (e.g. `background`, `card`, `text-primary`) to its CSS variable. To add a new colour: add the CSS variable on `:root`, add an entry in `tailwind.config.ts`.

Platform gradient utilities (`gradient-text-tiktok`, `gradient-btn-tiktok`, `tiktok-glitch`, `gradient-text-instagram`, `gradient-btn-instagram`) are in `globals.css`.

### PWA

- **`public/manifest.json`** — Makes the app installable. No `share_target` (Web Share Target API is not supported on iOS Safari/WebKit).
- **`public/sw.js`** — Cache-first for `/_next/static/` assets only. No share interception.
- **`components/InstallBanner.tsx`** — Mobile "Add to Home Screen" nudge, dismissable.
- **`components/RegisterSW.tsx`** — Registers `/sw.js` on mount (placed in `layout.tsx`).
- `next.config.mjs` `headers()` sets `Cache-Control: no-cache` for both `sw.js` and `manifest.json` (CDN must never cache the service worker).

---

## Key conventions

**Database migrations (self-migrating since v1.21):** No migration framework. The app migrates its own schema on every boot — `create_all` creates missing *tables*, then `_ensure_columns()` (SQLite, PRAGMA-based) or `_ensure_columns_pg()` (Postgres, `ADD COLUMN IF NOT EXISTS` — idempotent catalog no-ops once applied) adds missing *columns* on existing tables. **Adding a column = update `models.py` + add a guard to BOTH shims in `main.py`, then just deploy** — no manual Neon step. **Adding a new table = just add the model and deploy** — `create_all` handles it, no shim needed. RULES: the shims are ADDITIVE ONLY (new nullable/defaulted columns); destructive changes (DROP / RENAME / ALTER TYPE) stay manual and deliberate, run on Neon before deploy. In `_ensure_columns_pg`, append statements — never reorder or delete (each must stay valid against any historical schema). History: v1.13 added `seed_videos.rating`, `seed_videos.gemini_analysis`, `user_analyses.mode`; v1.19 `user_analyses.video_url`, `counts_fetched_at`; v1.20 `seed_videos.source`, `user_analyses.promoted_seed_id`; v1.24 `users.email/birth_year/seed_consent`, `user_analyses.pending_seed_consent`; v1.25 new table `password_reset_tokens` (no shim). NOTE: SQLite can't add a UNIQUE column via ALTER, so legacy local DBs enforce email uniqueness at the app layer only (signup checks `func.lower(User.email)`).

**Adding a new platform:** Add it to `VALID_PLATFORMS` in `routers/profile.py` and add a `_PLATFORM_CONTEXT` entry in `services/gemini.py`. Then add an entry to `PLATFORM_CONFIG` in `app/page.tsx`.

**Instagram vs TikTok signal difference:** Instagram does not expose view counts. All Instagram analysis uses `like_count` as the primary engagement signal throughout — Gemini prompt schema (`predicted_likes` not `predicted_views`), seed harvest (`view_count=None`), feedback modal (likes only), VerdictBanner, and improve page projections. Never assume `actual_views` or `predicted_views` are valid for Instagram.

**Gemini JSON output:** `response_mime_type="application/json"` forces clean JSON. Always guard with `_error_dict()` fallback so a bad model response never crashes the endpoint.

**Async + SQLite:** `aiosqlite` driver locally. Always use `async with engine.begin() as conn` or `AsyncSession` via `get_db()` — never `engine.execute()`.

---

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `backend/.env` | Google AI Studio key |
| `JWT_SECRET` | `backend/.env` | Token signing |
| `ADMIN_PASSWORD` | `backend/.env` | Admin panel (`X-Admin-Password` header) |
| `ALLOWED_ORIGINS` | `backend/.env` | CORS origins, comma-separated |
| `DATABASE_URL` | `backend/.env` (prod only) | Neon direct (non-pooler) connection string |
| `NEXT_PUBLIC_API_URL` | `frontend/.env.local` (prod only) | Backend URL; defaults to `http://localhost:8000` |
| `SMTP_HOST` | Render env | Brevo SMTP host (`smtp-relay.brevo.com`) |
| `SMTP_PORT` | Render env | Brevo SMTP port (`587`) |
| `SMTP_USER` | Render env | Brevo login (format: `xxx@smtp-brevo.com`) |
| `SMTP_PASS` | Render env | Brevo SMTP password |
| `EMAIL_FROM` | Render env | Sender display name + address (must match a verified Brevo sender); auto-derived as `Surge <{SMTP_USER}>` if unset — override this |
| `FRONTEND_URL` | Render env (optional) | Base URL for reset links; defaults to Vercel prod URL |
| `HIKERAPI_KEY` | Render env | HikerAPI key for Instagram seed harvesting (free tier: 100 req/month). Required for `POST /api/admin/harvest` with `platform=instagram`. |

## Production hosts

- **Backend:** Render — Docker build via `backend/Dockerfile`, blueprint at `backend/render.yaml`. Pending upgrade to Starter ($7/mo); until then, free tier spins down after ~15 min idle and `wakeBackend()` (called in UploadZone before uploads) mitigates cold starts for video analysis only — auth flows like forgot-password are not pre-warmed.
- **Frontend:** Vercel — auto-deploys from `main`. Live at `https://surge-chi-khaki.vercel.app`
- **Database:** Neon Postgres (AWS US East 1) — use the **direct** (non-pooler) connection string
- **Repo:** `https://github.com/rehanpalagiri/Surge` (private)
