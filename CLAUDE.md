# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

### Backend (FastAPI)
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000   # dev server with hot-reload
```
The venv is at `backend/venv/`. Never run `pip install` outside it. Backend reads `backend/.env` automatically via `python-dotenv`.

### Frontend (Next.js 15)
```bash
cd frontend
npm run dev       # dev server on :3000
npm run build     # production build (run before deploy to catch type errors)
npm run lint      # ESLint
```
`frontend/.env.local` must contain `NEXT_PUBLIC_API_URL=http://localhost:8000` for local dev.

### Running both together
```bash
# Terminal 1
cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000
# Terminal 2
cd frontend && npm run dev
```

## Architecture

### Request flow
```
Browser → Next.js (Vercel) → FastAPI (Render) → Neon Postgres
                                              → Google Gemini 2.5 Flash (video analysis)
```

### Backend structure
- **`main.py`** — FastAPI app, CORS, lifespan handler that runs `Base.metadata.create_all` then `_ensure_columns` (SQLite-only idempotent migration shim — skipped on Postgres where `create_all` handles everything)
- **`database.py`** — Builds the async SQLAlchemy engine: SQLite (default/local) or Postgres (production). Handles asyncpg-specific requirements: scheme normalisation, stripping `?sslmode=` from URL, passing SSL via `certifi` CA bundle in `connect_args`, disabling `statement_cache_size` for pooler connections.
- **`auth.py`** — `bcrypt` for password hashing (truncated to 72 bytes), `PyJWT` for tokens (30-day TTL). Two FastAPI dependencies: `require_user` (401 if no token) and `optional_user` (returns `None` if no token).
- **`models.py`** — Four tables: `users`, `seed_videos`, `user_analyses` (has `user_id` FK nullable for anonymous analyses), `fetch_status`
- **`routers/analyze.py`** — Core logic. `POST /api/analyze` accepts optional auth. `GET /api/analyses/{id}` returns `_to_locked()` for anonymous (only `verdict + predicted_views + locked:true`) or `_to_out()` for authenticated. `POST /api/analyses/{id}/claim` transfers anonymous analysis to a user account.
- **`routers/admin.py`** — Password-protected via `X-Admin-Password` header. Seed CRUD + `POST /api/admin/seed/from-url` (yt-dlp TikTok download, works locally only — blocked on Render).
- **`services/gemini.py`** — Uploads video to Gemini Files API, polls until `ACTIVE`, then calls `gemini-2.5-flash` with `response_mime_type="application/json"`. Builds a niche-aware prompt: uses same-niche seeds if ≥6 exist, falls back to global pool. Returns structured dict with scores, improvement plan, rewrites, projections.

### Frontend structure
- **App Router** (Next.js 15). All pages that need auth or URL params are `"use client"` components using `useParams()` — server components can't use `useParams()` and `params` is a Promise in Next 15 server components.
- **`lib/auth.ts`** — Token stored in `localStorage` under `viraliq_token`. `setToken`/`clearToken` dispatch a `viraliq-auth` CustomEvent so `Nav.tsx` reacts without a full page reload.
- **`lib/api.ts`** — All API calls. `authHeaders()` reads from localStorage. Every function throws on non-2xx with the status code in the message (callers detect 409 for duplicate username, etc).
- **`components/Nav.tsx`** — Listens to `viraliq-auth` + `storage` events to stay in sync across tabs.
- **Freemium gate** — `results/[id]/page.tsx` checks `scores_json.locked`. If true: shows blurred placeholder + unlock overlay + `UpsellModal` (auto-shown at 800ms, once per session via `sessionStorage`). The locked data is stripped server-side by `_to_locked()`, not just hidden in the UI.
- **Claim flow** — `signup/page.tsx` and `login/page.tsx` extract an analysis ID from `?next=/results/{id}` and call `claimAnalysis()` after auth succeeds.

## Key conventions

**Database migrations:** There is no migration framework. When adding columns to existing tables, add them to the SQLAlchemy model in `models.py` AND add a guard in `_ensure_columns()` in `main.py` (SQLite only — Postgres gets the column from `create_all` on a fresh DB; existing Postgres DBs need a manual `ALTER TABLE` or a proper migration tool).

**Admin auth:** `X-Admin-Password` header checked against `ADMIN_PASSWORD` env var. Not JWT — simple string comparison.

**Gemini JSON output:** `response_mime_type="application/json"` forces clean JSON. Always guard the parse with `_error_dict()` fallback so a bad response doesn't crash the endpoint.

**Async + SQLite:** `aiosqlite` driver for local. Never use `engine.execute()` — always `async with engine.begin() as conn` or `AsyncSession` via `get_db()`.

## Environment variables

| Variable | Where set | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `backend/.env` | Google AI Studio key |
| `JWT_SECRET` | `backend/.env` | Token signing secret |
| `ADMIN_PASSWORD` | `backend/.env` | Admin panel password |
| `ALLOWED_ORIGINS` | `backend/.env` | CORS origins (comma-separated) |
| `DATABASE_URL` | `backend/.env` (prod only) | Neon connection string; omit for local SQLite |
| `NEXT_PUBLIC_API_URL` | `frontend/.env.local` (prod only) | Backend URL; omit for local (defaults to `:8000`) |

## Production hosts
- **Backend:** Render — Docker build via `backend/Dockerfile`, blueprint at `backend/render.yaml`
- **Frontend:** Vercel — root directory set to `frontend/`
- **Database:** Neon Postgres (AWS US East 1) — direct (non-pooler) connection string
