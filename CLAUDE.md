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
- `users` — username + bcrypt password hash
- `user_profiles` — one row per (user, platform). Stores `handle`, `display_name`, `bio`, `target_audience`, `niche`. Unique constraint on `(user_id, platform)`. Platform is `"tiktok"` or `"instagram"`.
- `seed_videos` — reference TikTok/Instagram videos with `view_count`, `like_count`, `niche`, `posted_at` (original post date), `rating` (0–10 virality from Gemini seed analysis), `gemini_analysis` (full JSON writeup — the durable artifact; the video file is deleted after analysis). `performed` is a **deprecated vestigial column** (kept `nullable, default=False` so SQLAlchemy satisfies the old prod `NOT NULL` constraint on insert — do not read it).
- `user_analyses` — every analysis run. `user_id` nullable (anonymous). Has `platform` column (default `"tiktok"`) and `mode` (the **effective** mode that ran: `"quick" | "thinking" | "deep_thinking"`).
- `fetch_status` — log of yt-dlp auto-fetch attempts (success/fail)

**Key files:**
- **`main.py`** — FastAPI app, CORS, lifespan. Runs `Base.metadata.create_all` then `_ensure_columns` (SQLite-only migration shim). Registers all routers.
- **`database.py`** — Async SQLAlchemy engine. SQLite locally (no config), Neon Postgres in prod. asyncpg requires: scheme normalisation, stripping `?sslmode=` from URL, SSL via `certifi` CA bundle in `connect_args`, `statement_cache_size=0` for pooler.
- **`auth.py`** — `bcrypt` (direct, no passlib — passlib 4.x was incompatible), `PyJWT` 30-day tokens. Two deps: `require_user` (401) and `optional_user` (returns `None`).
- **`routers/analyze.py`** — `POST /api/analyze` (optional auth; `platform` + `mode` form fields, `ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime"}`). **Three-mode engine:** `resolve_mode()` computes the *effective* mode server-side and degrades gracefully (guests→Quick; Deep without a channel profile→Thinking; Thinking/Deep without usable seed buckets→Quick) so the results badge can never overclaim. Quick = raw video + caption only; Thinking adds the global seed reference + `profile_context`; Deep adds the creator channel profile. `PATCH /api/analyses/{id}/feedback` enforces hard sanity blocks (views ≥0, likes ≥0, likes ≤ views, views ≤ 500M). `GET /api/analyses/{id}` returns `_to_locked()` (verdict + predicted_views only) for anonymous or `_to_out()` for auth. `POST /api/analyses/{id}/claim` transfers anon analysis to account.
- **`services/channel_profile.py`** — `build_channel_profile(analyses)`: pure, unit-testable function over already-fetched `UserAnalysis` rows. Returns a prompt block (or `None` if <2 analyses). Two tiers: **A. Verified performance** (real `actual_views` rows — the prediction anchor) and **B. Self-assessment trends** (derived from past `scores_json`, framed explicitly as the system's own prior opinion). `recent_history` excludes past `predicted_views` to avoid the AI anchoring on its own guesses.
- **`services/seed_analysis.py`** — `analyze_seed_video()`: runs an AI-consumption-only seed-analysis prompt on an uploaded reference video, returns JSON with `virality_rating` + `seed_summary`. Reuses the `client`/`_PLATFORM_CONTEXT`/upload-poll-generate-delete pattern from `gemini.py`. Admin rejects (no row) on bad JSON or missing rating.
- **`services/niche_classifier.py`** — `classify_niche(raw)`: maps the user's free-text niche to one of `CANONICAL_NICHES` (20 labels) via a small text-only Gemini call. Exact case-insensitive matches skip the API call; any failure/timeout (10s) falls back to `"Lifestyle & Vlogs"` — classification can never block an analysis. The canonical label drives seed matching (`select_seed_examples` is an exact string compare); the raw text is stored on `user_analyses.niche` and passed to the prompt as `niche_raw` for specificity. **The admin seed form's `NICHES` list (`frontend/app/admin/page.tsx`) must stay in sync with `CANONICAL_NICHES`.**
- **`routers/profile.py`** — `GET /api/me/profile/{platform}` and `PUT /api/me/profile/{platform}` (upsert). Requires auth.
- **`routers/settings.py`** — `PATCH /api/me/username` and `PATCH /api/me/password`. Both require `current_password` in the request body for verification before applying the change.
- **`routers/admin.py`** — `X-Admin-Password` header auth. Seed CRUD + `POST /api/admin/seed/from-url` (yt-dlp — works locally only, blocked on Render datacenter IPs). Both upload paths run `analyze_seed_video` synchronously via `_analyze_and_persist_seed` (analyze → store `rating` + `gemini_analysis` → delete the file); a seed with no usable rating is **never** persisted (502, retry).
- **`services/gemini.py`** — Uploads video to Gemini Files API, polls until `ACTIVE`, calls `gemini-2.5-flash` with `response_mime_type="application/json"`. Key behaviours:
  1. **`select_seed_examples()`** — buckets seeds into HIGH (`rating ≥ 6`) / LOW (`rating ≤ 4`) by Gemini virality rating (disjoint, so no overlap; rating 5/None is dormant). The HIGH/LOW label is derived in code from the rating, never written by the model. Recency (`view_count × exp(-age_days/60)`) is only an intra-rating tiebreaker.
  2. **`_build_system_prompt(..., mode)`** — assembles the prompt per effective mode: Quick (no reference), Thinking (+ seed buckets + numeric benchmark), Deep (+ channel profile). Mode-specific `predicted_views` guidance.
  3. **Platform-aware** — `_PLATFORM_CONTEXT` dict has separate algorithm descriptions, key signals, and tips for TikTok vs Instagram (shared with `seed_analysis.py`).

### Frontend

**App Router** (Next.js 15). Any page using `useParams()`, `useSearchParams()`, or auth state must be `"use client"`. Server components cannot use these hooks and `params` is a Promise in server components.

**Key files:**
- **`app/page.tsx`** — `"use client"`. Platform switcher (TikTok / Instagram). `PLATFORM_CONFIG` drives all platform-specific visuals: `pageBg`, `badgeClass`, `accentClass`, `statColors`, `btnGradient`, etc. TikTok tab uses near-black bg + glitch text-shadow; Instagram uses purple-orange gradient.
- **`app/settings/page.tsx`** — Change username, change password. (Light mode was removed in v1.18 — the app is dark-only.)
- **`app/onboarding/page.tsx`** — Two-step profile setup after signup (TikTok → Instagram). Skippable.
- **`app/profile/page.tsx`** — Tabbed TikTok/Instagram profile editor.
- **`components/UploadZone.tsx`** — Accepts `platform` prop. Auto-fills bio from saved profile on platform change. Calls `wakeBackend()` before submitting to avoid cold-start "Load failed" on mobile. **Niche is free text** (max 80 chars, required — client blocks submit and server 400s on empty) with quick-tap suggestion chips; the backend classifies it to a canonical niche. Logged-in users get a **Quick / Thinking / Deep** depth selector (remembered in `localStorage` key `surge_mode`); guests see an inline "sign in for Thinking & Deep" link and always send `quick`. Passes `platform` + `mode` to `analyzeVideo()`. The results page shows a badge of the *effective* mode (`analysis.mode`).
- **`components/Nav.tsx`** — Hamburger menu on mobile (animated 3-bar → ✕ toggle, dropdown); full horizontal layout on desktop (`md+`). Listens to `surge-auth` + `storage` events. Auth links: My Projects, Profile, Settings, Log out. Carries the version badge (e.g. `v1.18`) — bump it on each release.
- **`lib/auth.ts`** — Token in `localStorage` as `surge_token` (auto-migrates from old `viraliq_token`). `setToken`/`clearToken` dispatch `surge-auth` CustomEvent.
- **`lib/api.ts`** — All API calls. `wakeBackend()` pings `/health` in a retry loop (up to 90s) before the heavy video upload to avoid mobile Safari "Load failed" errors on Render cold starts. `changeUsername` / `changePassword` call the settings endpoints.
- **`components/UpsellModal.tsx`** — Shown to anonymous users on locked results.
- **`components/VerdictBanner.tsx`** — Verdict + predicted views; shown in both locked and unlocked states.
- **`components/FeedbackModal.tsx`** — Thumbs up/down feedback. Calls `PATCH /api/analyses/{id}/feedback`.

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

**Database migrations:** No migration framework. Adding a column: update the model in `models.py` AND add a guard in `_ensure_columns()` in `main.py` (SQLite only). Existing Postgres DBs need a manual `ALTER TABLE` — new tables are created automatically by `create_all` on boot. **Run the Neon `ALTER TABLE` BEFORE deploying code that references the new column** — `create_all` never adds columns to existing tables, and a `select()` of the model will reference the missing column and 500. v1.13 added: `seed_videos.rating`, `seed_videos.gemini_analysis`, `user_analyses.mode`.

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
