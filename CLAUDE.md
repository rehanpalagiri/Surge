# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
## General Behavior

Do not make any changes until you have 95% confidence in what you need to build. Ask me follow-up questions until you reach that confidence.


Keep the Claude.md file under 200 lines
## Dev commands

```bash
# Backend
cd backend && source venv/bin/activate
uvicorn main:app --reload --port 8000   # reads backend/.env via python-dotenv

# Frontend
cd frontend
npm run dev        # :3000  (needs NEXT_PUBLIC_API_URL=http://localhost:8000 in .env.local)
npm run build      # catches TS + Next.js errors — run before every deploy
npm run lint       # ESLint via next lint
npx tsc --noEmit   # type-check without building
```

Both `backend/.env` and `frontend/.env.local` already exist locally. There are no automated tests — `npm run build` and `npx tsc --noEmit` are the only pre-deploy checks.

`fly.toml` and `render.yaml` exist in `backend/` but are unused — Railway is the actual host (configured via Railway dashboard, no config file needed).

---

## Architecture

```
Browser → Next.js (Vercel) → FastAPI (Railway) → Neon Postgres
                                               → Google Gemini 2.5 Flash
```

### Backend

**Models** (`models.py`):
- `users` — username, email (v1.24, primary login), `birth_year` + `birth_date` (YYYY-MM-DD, age gate: 13+; 13–17 forced `seed_consent="no"`), `seed_consent` (yes/no/ask)
- `user_profiles` — one row per (user, platform). Unique on `(user_id, platform)`.
- `seed_videos` — niche + `view_count` (NULL for Instagram) + `like_count` + `rating` (0–10) + `gemini_analysis` JSON. `performed` is a **deprecated vestigial column** — never read it.
- `user_analyses` — every analysis. `user_id` nullable (anon). Has `platform`, `mode` (effective: quick/thinking/deep_thinking), `pending_seed_consent`.
- `password_reset_tokens` — 6-digit code, 1h TTL, `used` bool.
- `fetch_status` — log of admin URL fetches (TikTok and Instagram). Surfaces the warning banner in the admin panel.

**Key backend files:**
- `main.py` — CORS, lifespan (`create_all` → `_ensure_columns`/`_ensure_columns_pg`), router registration, `_assert_prod_secrets()` (refuses prod boot with default JWT_SECRET/ADMIN_PASSWORD).
- `database.py` — Async SQLAlchemy. SQLite locally, Neon in prod. asyncpg needs: scheme normalisation, strip `?sslmode=` from URL, SSL via certifi, `statement_cache_size=0`.
- `auth.py` — `import bcrypt` direct (no passlib — `passlib[bcrypt]` in `requirements.txt` is a legacy leftover, not used by the code). PyJWT 30-day tokens. `require_user` (401) / `optional_user` (None). **`is_minor(user)` lives here — single canonical implementation; import from here, never reimplement inline.** Uses `birth_date` for exact day-level check, falls back to `birth_year` for legacy accounts.
- `routers/auth.py` — signup (`email+username+password+birth_date`), login (email or username), password reset (6-digit code via Brevo SMTP/`aiosmtplib`+certifi). Rate limits via `services/throttle.py`. Welcome email on signup.
- `routers/analyze.py` — `POST /api/analyze` (multipart, optional auth). Three-mode engine: Quick (video+caption), Thinking (+seed buckets+benchmark), Deep (+channel profile). `resolve_mode()` degrades gracefully. Gemini 429/403 caught before DB write → 503. `PATCH .../feedback`, `POST .../video-link` (TikTok only, auto-fetches stats, triggers seed promotion). `POST .../seed-consent`. Rate limit: 10 uploads/3h per user (+1 per verified link, max 20); guests capped at 3 per 3h per IP via `throttle.py` — rate checks run **before** any Gemini call. v1.28: Instagram analyses pass `creator_like_baseline` if ≥2 verified posts.
- `routers/profile.py` — GET/PUT `/api/me/profile/{platform}` (upsert).
- `routers/settings.py` — username/password change (both require current password; password minimum **8 chars**), consent (minors hard-blocked via `is_minor()`), `DELETE /api/me/account` (FK-order: reset tokens → profile → nullify analyses → user).
- `routers/admin.py` — `X-Admin-Password` header. Seed CRUD, `POST /api/admin/seed/from-url` (tikwm for TikTok, HikerAPI for Instagram), `POST /api/admin/harvest` (BackgroundTask), `GET /api/admin/harvest/status` → `{tiktok: ..., instagram: ...}`.
- `services/gemini.py` — Upload → poll ACTIVE → generate → delete. `google.genai.errors.ClientError` (NOT `google.api_core`). `select_seed_examples()`: HIGH (rating≥6) / LOW (rating≤4). Platform-aware: Instagram outputs `predicted_likes` only; TikTok outputs both `predicted_views` and `predicted_likes`. v1.28: personalized calibration block when `creator_like_baseline` present.
- `services/seed_harvest.py` — TikTok auto-harvest via tikwm. `NICHE_KEYWORDS` (50 niches × 3–4 keywords). `asyncio.gather + Semaphore(3)`. Dedupes via `vid:{video_id}` in notes.
- `services/instagram_harvest.py` — Instagram auto-harvest via HikerAPI (`HIKERAPI_KEY`). 100 req/month free tier: 2 keywords/niche × 50 niches = 100 calls. `asyncio.gather + Semaphore(3)`. Filters `media_type==2 && product_type=="clips"`. Dedupes via `ig:{media_pk}`.
- `services/seed_promote.py` — Background promotion of verified user videos into seed library. Idempotent via `promoted_seed_id`. Consent gate: minors never promote; `"ask"` parks (sets `pending_seed_consent`); `"yes"` proceeds.
- `services/niche_classifier.py` — Free-text → one of 50 `CANONICAL_NICHES` via small Gemini call. Fails → `"Lifestyle & Vlogs"`. Never blocks analysis.
- `services/channel_profile.py` — `build_channel_profile()`: returns a prompt block or `None` if <2 analyses (Deep then degrades to Thinking). Tier A = rows with real `actual_views` logged (gold anchor for predictions); Tier B = Surge's own past scores (labelled as internal opinion, not external proof).
- `services/throttle.py` — In-memory sliding-window rate limiter (`check_rate(key, max_hits, window_seconds)`).
- `services/tiktok_fetch.py` — tikwm.com metadata (views, likes, handle). Shared by admin + video-link endpoint.

**`scores_json` — three serialisation states:**

`UserAnalysis.scores_json` is always stored as the full Gemini response. The API (`_to_out` / `_to_locked`) serialises it differently per access level:

| State | When | Key fields |
|---|---|---|
| **Full** | Authenticated owner | All scores, improvement plan, rewrites, projections |
| **Locked** | Anonymous viewer | `verdict`, `predicted_views`, `predicted_likes`, `locked: true` |
| **Error** | Failed analysis | All scores 0, `error` key set, `verdict: "Needs work"` |

Frontend checks: `s.locked` → show paywall, `s.error` → show error screen, else full report.

### Frontend

Next.js 15 App Router. `"use client"` required for `useParams()`, `useSearchParams()`, auth state.

**Key frontend files:**
- `app/page.tsx` — Platform switcher (TikTok/Instagram). `PLATFORM_CONFIG` drives all platform visuals. Reads `?deleted=1` on mount to show account-deletion confirmation banner; cleans URL with `history.replaceState`.
- `app/signup/page.tsx` — email + username + password + birthday (MM/DD/YYYY, full date age check) + ToS checkbox.
- `app/login/page.tsx` — email or username in one field.
- `app/forgot-password/page.tsx` — 4-step reset: email → 6-digit OTP (auto-advance boxes) → new password → success. OTP uses `padEnd(6, " ")` (space, not empty string) so digit slots fill correctly; spaces are stripped in `handleChange`.
- `app/results/[id]/page.tsx` — Locked for anon (`_to_locked()`). `SeedConsentBanner` when `pending_seed_consent`.
- `app/results/[id]/improve/page.tsx` — Full improvement plan (auth-gated). Hook + caption rewrites, prioritized fixes, projected score.
- `app/projects/page.tsx` — "My Projects" — list of past analyses with actual vs predicted stats. TikTok rows have inline link/refresh; Instagram rows are display-only.
- `app/profile/page.tsx` — Per-platform profile editor (handle, bio, target audience, niche). Feeds Deep Thinking channel profile.
- `app/sample/page.tsx` — Static sample report (no auth). Shows a realistic fitness/TikTok result with all sections populated. Used for the "See a sample report" CTA on the landing page.
- `app/admin/page.tsx` — Seed panel. Platform toggle; per-platform harvest status. `NICHES` list must stay in sync with `CANONICAL_NICHES`.
- `app/settings/page.tsx` — Username/password (current password required for both; "Forgot your password?" link to reset flow), seed-consent card (minors excluded), `DeleteAccountCard`.
- `app/opengraph-image.tsx` — Brand OG card (1200×630, edge runtime). Shown when the homepage URL is shared.
- `app/results/[id]/opengraph-image.tsx` — Generic result share card (static — does not fetch per-result data; every result link shows the same card).
- `components/UploadZone.tsx` — `wakeBackend()` before upload. Niche chips always visible, always required. Quick/Thinking/Deep selector (localStorage `surge_mode`); guests always Quick. Advanced Settings toggle hides only caption + custom niche text input.
- `components/VerdictBanner.tsx` — Instagram: `predictedLikes` only (no views). TikTok: `predictedViews` + `predictedLikes`.
- `components/FeedbackModal.tsx` — TikTok: link-first (auto-fetch), manual toggle (views required, likes optional). Instagram: likes-only form (no views input — Instagram hides them; `actual_views` is not sent or stored for Instagram feedback).
- `components/UpsellModal.tsx` — Auto-shown ~800ms after an anonymous result loads (once per session via `sessionStorage`). Prompts signup to unlock full analysis.
- `components/ReportIssue.tsx` — Floating `?` button (fixed bottom-right, z-30). Opens modal with textarea; submits via `mailto:` with direct email fallback link.
- `lib/api.ts` — All API calls. `wakeBackend()` retries `/health` up to 90s. `HarvestStatus = {tiktok?, instagram?}`.
- `lib/auth.ts` — JWT in `localStorage` as `surge_token`. Dispatches `surge-auth` event.
- `components/Nav.tsx` — Hamburger on mobile, horizontal on desktop. Bump version badge on each release.

**Theme:** Dark-only. CSS variables on `:root` in `globals.css`; mapped in `tailwind.config.ts`. Platform gradient utilities in `globals.css`.

**PWA:** `manifest.json` + `sw.js` (cache-first for `/_next/static/` only) + `InstallBanner.tsx`. `next.config.mjs` sets `Cache-Control: no-cache` for sw.js + manifest.

**Analytics:** `@vercel/analytics` — `<Analytics />` in `app/layout.tsx`. No config needed; tracks page views automatically once deployed to Vercel.

---

## Key conventions

**Self-migrating schema:** No migration framework. On boot: `create_all` (new tables) → `_ensure_columns` (SQLite, PRAGMA) or `_ensure_columns_pg` (Postgres, `ADD COLUMN IF NOT EXISTS`). **To add a column:** update `models.py` + add guard to BOTH shims + deploy. **To add a table:** just add the model + deploy. Shims are ADDITIVE ONLY — destructive changes are manual on Neon before deploy. SQLite can't add UNIQUE columns via ALTER; email uniqueness falls back to app-layer check.

**Age gate:** Signup collects full birthday (MM/DD/YYYY → sent as YYYY-MM-DD ISO). Backend parses with `date.fromisoformat`, computes exact age. `is_minor()` in `auth.py` is the single source of truth for all age checks — 4 callers import from there. Never reimplement inline.

**Adding a platform:** Add to `VALID_PLATFORMS` in `routers/profile.py`, `_PLATFORM_CONTEXT` in `services/gemini.py`, and `PLATFORM_CONFIG` in `app/page.tsx`.

**Instagram vs TikTok:** Instagram hides view counts everywhere — `view_count=None` on seeds, `predicted_likes` not `predicted_views` in Gemini output, likes-only feedback (no `actual_views` sent or stored), no views in VerdictBanner or improve page. `creator_like_baseline` uses `actual_likes` and works for both platforms. `build_channel_profile()`'s Tier A requires `actual_views is not None`, so Instagram analyses never qualify — Deep mode for Instagram always degrades to Thinking.

**Mode degradation ladder** (`resolve_mode()` in `routers/analyze.py`):
1. Guest → always Quick (no auth)
2. Deep requested + `build_channel_profile()` returned non-None → Deep
3. Thinking or Deep requested + usable seeds exist → Thinking
4. Otherwise → Quick

The results badge reads `analysis.mode` (effective), never the requested mode.

**Score color thresholds — consistent everywhere:** ≥7 = green (`text-success`/`bg-success`), ≥4 = yellow (`text-warning`/`bg-warning`), <4 = red (`text-danger`/`bg-danger`). Used in `ScoreBar`, `scoreColor()` in projects/results pages, and `scoreBorder()` in the improve page.

**Gemini:** Always guard with `_error_dict()`. `google.genai.errors.ClientError` (not `google.api_core`). Re-raise 429/403 before writing to DB.

**Async:** Always use `AsyncSession` via `get_db()` or `async with AsyncSessionLocal()` — never synchronous engine calls.

---

## Environment variables

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio key |
| `JWT_SECRET` | Token signing (must be strong in prod) |
| `ADMIN_PASSWORD` | Admin panel header auth (must be strong in prod) |
| `ALLOWED_ORIGINS` | CORS origins, comma-separated |
| `DATABASE_URL` | Neon direct (non-pooler) connection string (prod only) |
| `NEXT_PUBLIC_API_URL` | Backend URL (defaults to `http://localhost:8000`) |
| `SMTP_HOST/PORT/USER/PASS` | Brevo SMTP (`smtp-relay.brevo.com:587`) |
| `EMAIL_FROM` | Sender display + address (verified Brevo sender) |
| `FRONTEND_URL` | Base URL for reset links (defaults to Vercel prod URL) |
| `HIKERAPI_KEY` | Instagram seed harvest (HikerAPI, 100 req/month free) |

## Production

- **Backend:** Railway — Docker (`backend/Dockerfile`, configured in Railway dashboard, root directory = `backend`). No `railway.toml` needed — Railway auto-detects the Dockerfile.
- **Frontend:** Vercel — auto-deploys from `main`. `https://surge-chi-khaki.vercel.app`
- **Database:** Neon Postgres (AWS US East 1) — use direct (non-pooler) URL
- **Repo:** `https://github.com/rehanpalagiri/Surge` (private)

## Deploy discipline — IMPORTANT

Railway runs on a usage credit model. Every backend deploy rebuilds the Docker image and costs bandwidth. **30 deploys burned through Render's free tier** — don't repeat this pattern.

**Rules:**
1. **Batch backend changes.** Never push a single-line backend fix. Accumulate multiple changes and push once.
2. **Test locally before every backend push.** Run `uvicorn main:app --reload` and manually verify the change works. A push that requires a follow-up fix = 2 deploys for 1 fix.
3. **Frontend deploys are free** (Vercel bandwidth is generous). The discipline applies to backend (`main` branch pushes that touch `backend/`).
4. **Schema changes + code changes = one push.** Don't push the schema change, verify, then push the code. Do both together.
5. **Never push to fix a typo or log statement.** Fix locally, bundle it into the next real change.

**Before any backend push, ask:** "Can I combine this with anything else that's pending?" If yes, wait.
