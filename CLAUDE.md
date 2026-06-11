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

### Backend — five tables, six routers

**Models (`models.py`):**
- `users` — username (display name) + bcrypt password hash. v1.24: `email` (unique, primary login identifier; nullable for pre-1.24 accounts), `birth_year` (age gate: 13+ to sign up), `seed_consent` (`"yes" | "no" | "ask"` — minors 13–17 are forced to `"no"` permanently; adults default `"ask"`).
- `user_profiles` — one row per (user, platform). Stores `handle`, `display_name`, `bio`, `target_audience`, `niche`. Unique constraint on `(user_id, platform)`. Platform is `"tiktok"` or `"instagram"`.
- `seed_videos` — reference TikTok/Instagram videos with `view_count`, `like_count`, `niche`, `posted_at` (original post date), `rating` (0–10 virality from Gemini seed analysis), `gemini_analysis` (full JSON writeup — the durable artifact; the video file is deleted after analysis). `performed` is a **deprecated vestigial column** (kept `nullable, default=False` so SQLAlchemy satisfies the old prod `NOT NULL` constraint on insert — do not read it).
- `user_analyses` — every analysis run. `user_id` nullable (anonymous). Has `platform` column (default `"tiktok"`), `mode` (the **effective** mode that ran: `"quick" | "thinking" | "deep_thinking"`), and `pending_seed_consent` (v1.24 — verified link arrived while the owner's `seed_consent` was `"ask"`; the results page shows the consent banner).
- `fetch_status` — log of yt-dlp auto-fetch attempts (success/fail)

**Key files:**
- **`main.py`** — FastAPI app, CORS, lifespan. Runs `Base.metadata.create_all` then `_ensure_columns` (SQLite-only migration shim). Registers all routers.
- **`database.py`** — Async SQLAlchemy engine. SQLite locally (no config), Neon Postgres in prod. asyncpg requires: scheme normalisation, stripping `?sslmode=` from URL, SSL via `certifi` CA bundle in `connect_args`, `statement_cache_size=0` for pooler.
- **`auth.py`** — `bcrypt` (direct, no passlib — passlib 4.x was incompatible), `PyJWT` 30-day tokens. Two deps: `require_user` (401) and `optional_user` (returns `None`).
- **`routers/auth.py`** (v1.24) — signup requires `email` (validated, stored lowercase, unique) + `username` + `password` (min 8) + `birth_year` (under-13 → 403; 13–17 → `seed_consent="no"` locked; 18+ → `"ask"`). Login accepts **email OR username** in the same field. `is_minor(user)` helper (birth_year → under 18; legacy `NULL` birth_year = adult). `/me` returns the computed `is_minor`.
- **`routers/analyze.py`** — `POST /api/analyze` (optional auth; `platform` + `mode` form fields, `ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime"}`). **Three-mode engine:** `resolve_mode()` computes the *effective* mode server-side and degrades gracefully (guests→Quick; Deep without a channel profile→Thinking; Thinking/Deep without usable seed buckets→Quick) so the results badge can never overclaim. Quick = raw video + caption only; Thinking adds the global seed reference + `profile_context`; Deep adds the creator channel profile. `PATCH /api/analyses/{id}/feedback` enforces hard sanity blocks (views ≥0, likes ≥0, likes ≤ views, views ≤ 500M). `POST /api/analyses/{id}/video-link` (v1.19, TikTok only) attaches the user's posted video URL and auto-fetches real views/likes via `tiktok_fetch`; `url=None` refreshes from the stored link (24h cooldown → 429). Soft ownership check: 422 if the saved profile handle and the video's author handle both exist and differ. **On a successful link (v1.20) it schedules a background task (`services.seed_promote`) that auto-promotes the verified video into the seed library** — idempotent via `user_analyses.promoted_seed_id`. `GET /api/analyses/{id}` returns `_to_locked()` (verdict + predicted_views only) for anonymous or `_to_out()` for auth. `POST /api/analyses/{id}/claim` transfers anon analysis to account. **Rate limit (v1.23):** `services/rate_limit.py` — auth'd users get 10 uploads per rolling 3h window + 1 bonus credit per all-time verified link (capped +10, so max 20/3h); over-limit → 429; guests unmetered. `GET /api/me/rate-limit` feeds the UploadZone status bar. **Seed consent (v1.24):** `POST /api/analyses/{id}/seed-consent` (`{allow, remember?}`) answers the results-page banner — `allow=true` re-runs `promote_analysis_to_seed` with `consent_override=True`; `remember` persists the choice account-wide (minors hard-blocked).
- **`services/channel_profile.py`** — `build_channel_profile(analyses)`: pure, unit-testable function over already-fetched `UserAnalysis` rows. Returns a prompt block (or `None` if <2 analyses). Two tiers: **A. Verified performance** (real `actual_views` rows — the prediction anchor) and **B. Self-assessment trends** (derived from past `scores_json`, framed explicitly as the system's own prior opinion). `recent_history` excludes past `predicted_views` to avoid the AI anchoring on its own guesses.
- **`services/seed_analysis.py`** — `analyze_seed_video()`: runs an AI-consumption-only seed-analysis prompt on an uploaded reference video, returns JSON with `virality_rating` + `seed_summary`. Reuses the `client`/`_PLATFORM_CONTEXT`/upload-poll-generate-delete pattern from `gemini.py`. Admin rejects (no row) on bad JSON or missing rating.
- **`services/niche_classifier.py`** — `classify_niche(raw)`: maps the user's free-text niche to one of `CANONICAL_NICHES` (50 labels since v1.22) via a small text-only Gemini call. Exact case-insensitive matches skip the API call; any failure/timeout (10s) falls back to `"Lifestyle & Vlogs"` — classification can never block an analysis. The canonical label drives seed matching (`select_seed_examples` is an exact string compare); the raw text is stored on `user_analyses.niche` and passed to the prompt as `niche_raw` for specificity. **The admin seed form's `NICHES` list (`frontend/app/admin/page.tsx`) must stay in sync with `CANONICAL_NICHES`.**
- **`routers/profile.py`** — `GET /api/me/profile/{platform}` and `PUT /api/me/profile/{platform}` (upsert). Requires auth.
- **`routers/settings.py`** — `PATCH /api/me/username` and `PATCH /api/me/password`. Both require `current_password` in the request body for verification before applying the change. v1.24: `GET /api/me/consent` (minors always read `"no"`) and `PATCH /api/me/consent` (403 for minors; values `yes|no|ask`).
- **`routers/admin.py`** — `X-Admin-Password` header auth. Seed CRUD + `POST /api/admin/seed/from-url` (tikwm.com for TikTok — free/keyless, works from any IP; EaseApi on RapidAPI for Instagram — 20 req/month free cap). Both upload paths run `analyze_seed_video` synchronously via `_analyze_and_persist_seed` (analyze → store `rating` + `gemini_analysis` → delete the file); a seed with no usable rating is **never** persisted (502, retry). v1.22 ("Door A"): `POST /api/admin/harvest` (BackgroundTask → `services/seed_harvest.harvest_all`) + `GET /api/admin/harvest/status` (in-memory last-run summary).
- **`services/seed_harvest.py`** (v1.22, "Door A") — automated seed harvesting: `NICHE_KEYWORDS` maps all 50 canonical niches to 3–4 tikwm search keywords (**must stay in lockstep with `CANONICAL_NICHES`**). Per niche: `GET tikwm /api/feed/search` → filter `play_count ≥ min_views` (default 500K) → dedupe via `vid:{video_id}` tag in `notes` → download the short-lived `play` URL → `analyze_seed_video` → persist with `source="harvest"`. ~1.2s sleep between searches (tikwm ~1 req/sec). Triggered from the admin page button or the weekly GitHub Actions cron (`.github/workflows/harvest.yml`, Mondays 06:00 UTC, needs `ADMIN_PASSWORD` repo secret).
- **`services/tiktok_fetch.py`** — `fetch_tiktok(url)`: public TikTok metadata via tikwm.com (views, likes, caption, posted_at, author_handle). Raises `ValueError` on failure. Shared by the admin seed fetcher and the user video-link endpoint. `is_tiktok_url()` validates links.
- **`services/seed_promote.py`** (v1.20, "Door B") — `promote_analysis_to_seed(analysis_id)`: background task fired after a verified user video-link. Re-fetches the video (tikwm), classifies the niche to canonical, downloads + runs `analyze_seed_video`, and persists a `SeedVideo` with `source="user"` — real verified counts make these the *best* seed signal. Idempotent (`user_analyses.promoted_seed_id`), self-contained DB session (request session is closed by then), every failure logged + swallowed (promotion never breaks the user's stat-sync). Only the **verified link** path promotes — manual feedback entry never does (un-verifiable). **Consent gate (v1.24):** before the heavy phase it loads the owner — minors never promote; `seed_consent="no"` → skip; `"ask"` → sets `pending_seed_consent=True` and parks (the results-page banner + `/seed-consent` endpoint resume with `consent_override=True`); `"yes"` → proceeds.
- **`services/gemini.py`** — Uploads video to Gemini Files API, polls until `ACTIVE`, calls `gemini-2.5-flash` with `response_mime_type="application/json"`. Key behaviours:
  1. **`select_seed_examples()`** — buckets seeds into HIGH (`rating ≥ 6`) / LOW (`rating ≤ 4`) by Gemini virality rating (disjoint, so no overlap; rating 5/None is dormant). The HIGH/LOW label is derived in code from the rating, never written by the model. Recency (`view_count × exp(-age_days/60)`) is only an intra-rating tiebreaker.
  2. **`_build_system_prompt(..., mode)`** — assembles the prompt per effective mode: Quick (no reference), Thinking (+ seed buckets + numeric benchmark), Deep (+ channel profile). Mode-specific `predicted_views` guidance.
  3. **Platform-aware** — `_PLATFORM_CONTEXT` dict has separate algorithm descriptions, key signals, and tips for TikTok vs Instagram (shared with `seed_analysis.py`).

### Frontend

**App Router** (Next.js 15). Any page using `useParams()`, `useSearchParams()`, or auth state must be `"use client"`. Server components cannot use these hooks and `params` is a Promise in server components.

**Key files:**
- **`app/page.tsx`** — `"use client"`. Platform switcher (TikTok / Instagram). `PLATFORM_CONFIG` drives all platform-specific visuals: `pageBg`, `badgeClass`, `accentClass`, `statColors`, `btnGradient`, etc. TikTok tab uses near-black bg + glitch text-shadow; Instagram uses purple-orange gradient.
- **`app/settings/page.tsx`** — Change username, change password, and (v1.24) the "Data & Privacy" seed-consent card: minors see a static exclusion note; adults get yes/ask/no radios (optimistic update, reverts on failure). Footer links to /privacy and /terms. (Light mode was removed in v1.18 — the app is dark-only.)
- **`app/privacy/page.tsx` + `app/terms/page.tsx`** (v1.24) — static server-rendered legal pages. Privacy has the `#seed-pool` anchor the consent UIs link to; effective dates are hardcoded — update them when the policy materially changes. Contact: surgeprivacy@gmail.com. Home page footer links to both.
- **`app/signup/page.tsx`** — email + username + password (min 8) + birth year + required ToS/Privacy checkbox. Inline under-13 error as soon as a 4-digit year is typed; server errors surfaced via `apiErrorDetail`. Login accepts username or email in one field.
- **`app/results/[id]/page.tsx`** — `SeedConsentBanner`: dismissible card shown when `analysis.pending_seed_consent` (owner's setting is "ask"). Buttons: Yes / No thanks / Always yes / Always no — any click dismisses immediately and fires `seedConsentDecision` best-effort.
- **`app/onboarding/page.tsx`** — Two-step profile setup after signup (TikTok → Instagram). Skippable.
- **`app/profile/page.tsx`** — Tabbed TikTok/Instagram profile editor.
- **`components/UploadZone.tsx`** — Accepts `platform` prop. Auto-fills bio from saved profile on platform change. Calls `wakeBackend()` before submitting to avoid cold-start "Load failed" on mobile. **Niche is free text** (max 80 chars, required — client blocks submit and server 400s on empty) with quick-tap suggestion chips; the backend classifies it to a canonical niche. Logged-in users get a **Quick / Thinking / Deep** depth selector (remembered in `localStorage` key `surge_mode`); guests see an inline "sign in for Thinking & Deep" link and always send `quick`. Passes `platform` + `mode` to `analyzeVideo()`. The results page shows a badge of the *effective* mode (`analysis.mode`).
- **`components/Nav.tsx`** — Hamburger menu on mobile (animated 3-bar → ✕ toggle, dropdown); full horizontal layout on desktop (`md+`). Listens to `surge-auth` + `storage` events. Auth links: My Projects, Profile, Settings, Log out. Carries the version badge (e.g. `v1.18`) — bump it on each release.
- **`lib/auth.ts`** — Token in `localStorage` as `surge_token` (auto-migrates from old `viraliq_token`). `setToken`/`clearToken` dispatch `surge-auth` CustomEvent.
- **`lib/api.ts`** — All API calls. `wakeBackend()` pings `/health` in a retry loop (up to 90s) before the heavy video upload to avoid mobile Safari "Load failed" errors on Render cold starts. `changeUsername` / `changePassword` call the settings endpoints.
- **`components/UpsellModal.tsx`** — Shown to anonymous users on locked results.
- **`components/VerdictBanner.tsx`** — Verdict + predicted views; shown in both locked and unlocked states.
- **`components/FeedbackModal.tsx`** — Actual-performance entry on the results page. TikTok: link-first — paste the posted video URL → `POST /api/analyses/{id}/video-link` auto-fetches real stats (manual entry remains as a toggle). Instagram: manual views/likes via `PATCH /api/analyses/{id}/feedback`. My Projects cards (TikTok) also carry a link/refresh affordance per card.

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

**Database migrations (self-migrating since v1.21):** No migration framework. The app migrates its own schema on every boot — `create_all` creates missing *tables*, then `_ensure_columns()` (SQLite, PRAGMA-based) or `_ensure_columns_pg()` (Postgres, `ADD COLUMN IF NOT EXISTS` — idempotent catalog no-ops once applied) adds missing *columns* on existing tables. **Adding a column = update `models.py` + add a guard to BOTH shims in `main.py`, then just deploy** — no manual Neon step. RULES: the shims are ADDITIVE ONLY (new nullable/defaulted columns); destructive changes (DROP / RENAME / ALTER TYPE) stay manual and deliberate, run on Neon before deploy. In `_ensure_columns_pg`, append statements — never reorder or delete (each must stay valid against any historical schema). History: v1.13 added `seed_videos.rating`, `seed_videos.gemini_analysis`, `user_analyses.mode`; v1.19 `user_analyses.video_url`, `counts_fetched_at`; v1.20 `seed_videos.source`, `user_analyses.promoted_seed_id`; v1.24 `users.email/birth_year/seed_consent`, `user_analyses.pending_seed_consent`. NOTE: SQLite can't add a UNIQUE column via ALTER, so legacy local DBs enforce email uniqueness at the app layer only (signup checks `func.lower(User.email)`).

**Adding a new platform:** Add it to `VALID_PLATFORMS` in `routers/profile.py` and add a `_PLATFORM_CONTEXT` entry in `services/gemini.py`. Then add an entry to `PLATFORM_CONFIG` in `app/page.tsx`.

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

## Production hosts

- **Backend:** Render — Docker build via `backend/Dockerfile`, blueprint at `backend/render.yaml`. Free tier spins down after ~15 min idle; `wakeBackend()` handles client-side cold-start mitigation.
- **Frontend:** Vercel — auto-deploys from `main`. Live at `https://surge-chi-khaki.vercel.app`
- **Database:** Neon Postgres (AWS US East 1) — use the **direct** (non-pooler) connection string
- **Repo:** `https://github.com/rehanpalagiri/Surge`
- **Keep-alive:** `.github/workflows/keep-alive.yml` pings `${{ secrets.BACKEND_HEALTH_URL }}` every 10 min (skips 12am–6am Pacific). Requires `BACKEND_HEALTH_URL` repo secret to be set.
