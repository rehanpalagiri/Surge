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
Browser → Next.js (Netlify) → FastAPI (Render) → Neon Postgres
                                               → Google Gemini 2.5 Flash (video analysis)
```

### Backend — five tables, six routers

**Models (`models.py`):**
- `users` — username + bcrypt password hash
- `user_profiles` — one row per (user, platform). Stores `handle`, `display_name`, `bio`, `target_audience`, `niche`. Unique constraint on `(user_id, platform)`. Platform is `"tiktok"` or `"instagram"`.
- `seed_videos` — reference TikTok/Instagram videos with `view_count`, `like_count`, `niche`, `posted_at` (original post date), `performed` flag
- `user_analyses` — every analysis run. `user_id` nullable (anonymous). Has `platform` column (default `"tiktok"`).
- `fetch_status` — log of yt-dlp auto-fetch attempts (success/fail)

**Key files:**
- **`main.py`** — FastAPI app, CORS, lifespan. Runs `Base.metadata.create_all` then `_ensure_columns` (SQLite-only migration shim). Registers all routers.
- **`database.py`** — Async SQLAlchemy engine. SQLite locally (no config), Neon Postgres in prod. asyncpg requires: scheme normalisation, stripping `?sslmode=` from URL, SSL via `certifi` CA bundle in `connect_args`, `statement_cache_size=0` for pooler.
- **`auth.py`** — `bcrypt` (direct, no passlib — passlib 4.x was incompatible), `PyJWT` 30-day tokens. Two deps: `require_user` (401) and `optional_user` (returns `None`).
- **`routers/analyze.py`** — `POST /api/analyze` (optional auth, accepts `platform` form field). Loads the user's `UserProfile` for that platform and builds a `profile_context` string injected into Gemini. Saves analysis with `platform`. `GET /api/analyses/{id}` returns `_to_locked()` (verdict + predicted_views only) for anonymous or `_to_out()` for auth. `POST /api/analyses/{id}/claim` transfers anon analysis to account.
- **`routers/profile.py`** — `GET /api/me/profile/{platform}` and `PUT /api/me/profile/{platform}` (upsert). Requires auth.
- **`routers/admin.py`** — `X-Admin-Password` header auth. Seed CRUD + `POST /api/admin/seed/from-url` (yt-dlp — works locally only, blocked on Render datacenter IPs).
- **`services/gemini.py`** — Uploads video to Gemini Files API, polls until `ACTIVE`, calls `gemini-2.5-flash` with `response_mime_type="application/json"`. Two key behaviours:
  1. **Recency weighting** — seeds sorted by `view_count × exp(-age_days/60)` so recent videos rank above old viral ones. Uses `posted_at` if set, falls back to `created_at`.
  2. **Platform-aware prompt** — `_PLATFORM_CONTEXT` dict has separate algorithm descriptions, key signals, and tips for TikTok (FYP, watch time, sounds) vs Instagram (Explore, saves/shares, aesthetic, thumbnail). The user's saved profile context is appended to the prompt.

### Frontend

**App Router** (Next.js 15). Any page using `useParams()`, `useSearchParams()`, or auth state must be `"use client"`. Server components cannot use these hooks and `params` is a Promise in server components.

**Key files:**
- **`app/page.tsx`** — `"use client"`. Platform switcher (🎵 TikTok / 📸 Instagram) tabs at the top. Switches headline copy, badge, and passes `platform` prop to `UploadZone`.
- **`app/onboarding/page.tsx`** — Two-step profile setup shown after signup (TikTok → Instagram). Each step saves via `PUT /api/me/profile/{platform}`. Skippable. Redirected here from signup unless user came from a results page.
- **`app/profile/page.tsx`** — Tabbed TikTok/Instagram profile editor. Loads both profiles on mount, saves on button click.
- **`components/UploadZone.tsx`** — Accepts `platform` prop. On platform change, auto-fills the bio field from the user's saved profile (`getProfile(platform)`). Passes `platform` to `analyzeVideo()`.
- **`lib/auth.ts`** — Token in `localStorage` as `viraliq_token`. `setToken`/`clearToken` dispatch `viraliq-auth` CustomEvent so Nav updates without page reload.
- **`lib/api.ts`** — All API calls. Throws on non-2xx with status in message. `analyzeVideo` now takes `platform` param. `getProfile` / `upsertProfile` for profile CRUD.
- **`components/Nav.tsx`** — Listens to `viraliq-auth` + `storage` events. Shows My Projects + Profile + Log out when authenticated.

**Freemium gate:** `results/[id]/page.tsx` checks `scores_json.locked`. Locked data is stripped server-side in `_to_locked()` — full scores never leave the backend for anonymous users.

**Claim flow:** After signup/login, if `?next=/results/{id}` is present, calls `claimAnalysis(id)` to transfer the anonymous analysis to the new account.

---

## Key conventions

**Database migrations:** No migration framework. Adding a column: update the model in `models.py` AND add a guard in `_ensure_columns()` in `main.py` (SQLite only). Existing Postgres DBs need a manual `ALTER TABLE` — new tables are created automatically by `create_all` on boot.

**Adding a new platform:** Add it to `VALID_PLATFORMS` in `routers/profile.py` and add a `_PLATFORM_CONTEXT` entry in `services/gemini.py`.

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

- **Backend:** Render — Docker build via `backend/Dockerfile`, blueprint at `backend/render.yaml`
- **Frontend:** Netlify — config in `netlify.toml` at repo root (base: `frontend`, plugin: `@netlify/plugin-nextjs`)
- **Database:** Neon Postgres (AWS US East 1) — use the **direct** (non-pooler) connection string
- **Repo:** `https://github.com/rehanpalagiri/Surge`
