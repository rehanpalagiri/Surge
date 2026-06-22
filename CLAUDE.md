# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
## General Behavior

Do not make any changes until you have 95% confidence in what you need to build. Ask me follow-up questions until you reach that confidence.

Make sure to Update this Claud.md file whenever needed, and you should be updating it constantly to make sure it is up to date.


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
- `seed_videos` — niche + `view_count` (NULL for Instagram) + `like_count` + `rating` (0–10, anchored to **like-rate** = likes/views, NOT raw views — so reach-driven videos aren't mislabeled as good content) + `gemini_analysis` JSON (now includes `performance_driver` = content/distribution/mixed/unclear + `driver_confidence`). `performed` is a **deprecated vestigial column** — never read it.
- `user_analyses` — every analysis. `user_id` nullable (anon). Has `platform`, `mode` (effective: quick/thinking/deep_thinking), `pending_seed_consent`, `correction_json` (Gemini audit of predicted-vs-actual, set by `audit_prediction` once a linked video matures), `calibration_version` (Build #3: which calibration note nudged this prediction; 0 = un-nudged). **`niche`** = the user's raw words (display only); **`canonical_niche`** = the classifier label that drives ALL niche-keyed lookups (esp. calibration grouping/loading) so free-text inputs don't fragment.
- `calibration_notes` — Build #3 mistake-summarization. One bounded calibration nudge per (platform, niche) or `"GLOBAL"`. `note_json` (clamped) + `sample_count` + `generated_at`. Unique on (platform, niche).
- `password_reset_tokens` — 6-digit code, 1h TTL, `used` bool.
- `fetch_status` — log of admin URL fetches (TikTok and Instagram). Surfaces the warning banner in the admin panel.

**Key backend files:**
- `main.py` — CORS, lifespan (`create_all` → `_ensure_columns`/`_ensure_columns_pg`), router registration, `_assert_prod_secrets()` (refuses prod boot with default JWT_SECRET/ADMIN_PASSWORD).
- `database.py` — Async SQLAlchemy. SQLite locally, Neon in prod. asyncpg needs: scheme normalisation, strip `?sslmode=` from URL, SSL via certifi, `statement_cache_size=0`.
- `auth.py` — `import bcrypt` direct (no passlib — `passlib[bcrypt]` in `requirements.txt` is a legacy leftover, not used by the code). PyJWT 30-day tokens. `require_user` (401) / `optional_user` (None). **`is_minor(user)` lives here — single canonical implementation; import from here, never reimplement inline.** Uses `birth_date` for exact day-level check, falls back to `birth_year` for legacy accounts.
- `routers/auth.py` — signup (`email+username+password+birth_date`), login (email or username), password reset (6-digit code via Brevo SMTP/`aiosmtplib`+certifi). Rate limits via `services/throttle.py`. Welcome email on signup.
- `routers/analyze.py` — `POST /api/analyze` (multipart, optional auth). Three-mode engine: Quick (video+caption), Thinking (+seed buckets+benchmark), Deep (+channel profile). `resolve_mode()` degrades gracefully. Gemini 429/403 caught before DB write → 503. `PATCH .../feedback`, `POST .../video-link` (TikTok only, auto-fetches stats, triggers seed promotion + `audit_prediction`; fires on refresh too). `POST .../seed-consent`. Rate limit: 10 uploads/3h per user (+1 per verified link, max 20); guests capped at 3 per 3h per IP via `throttle.py` — rate checks run **before** any Gemini call. v1.28: Instagram analyses pass `creator_like_baseline` if ≥2 verified posts.
- `routers/profile.py` — GET/PUT `/api/me/profile/{platform}` (upsert).
- `routers/settings.py` — username/password change (both require current password; password minimum **8 chars**), consent (minors hard-blocked via `is_minor()`), `DELETE /api/me/account` (FK-order: reset tokens → profile → nullify analyses → user).
- `routers/admin.py` — `X-Admin-Password` header. Seed CRUD, `POST /api/admin/seed/from-url` (tikwm for TikTok, HikerAPI for Instagram), `POST /api/admin/harvest` (BackgroundTask), `GET /api/admin/harvest/status` → `{tiktok: ..., instagram: ...}`. Build #3: `POST /api/admin/calibration/generate` (regen notes from corrections; `niche` optional, `"GLOBAL"` valid) + `GET /api/admin/calibration` (list).
- `services/gemini.py` — Upload → poll ACTIVE → generate → delete. `google.genai.errors.ClientError` (NOT `google.api_core`). `select_seed_examples()`: HIGH (rating≥6) / LOW (rating≤4). Platform-aware: Instagram outputs `predicted_likes` only; TikTok outputs both `predicted_views` and `predicted_likes`. v1.28: personalized calibration block when `creator_like_baseline` present. Build #3: injects a `calibration_note` directive (Thinking/Deep only, gated by `_calibration_applies`) as soft guidance + stamps `calibration_version` onto the result.
- `services/seed_analysis.py` — `_build_seed_prompt` + `analyze_seed_video` + `score_outcome`. The ONE seed pipeline, shared by all 3 seed sources (admin, harvest, user-promote). **Split architecture (anti-anchoring):** Gemini scores ONLY the 6 craft dimensions, *blind to the counts* (the prompt never contains views/likes), at `temperature=0`. The outcome — `virality_rating` + `performance_driver` + `driver_confidence` — is computed in CODE by `score_outcome(view_count, like_count)`, NOT the LLM, so it's deterministic and the rules are *enforced not requested*: like-rate bands (≥10%→9 content, 5-10%→7, 2-5%→5 mixed, <2%→3 distribution); thin samples (`view_count < LIKE_RATE_MIN_VIEWS`=10k)→5/unclear/low; Instagram (no views)→absolute like bands, driver `unclear`. Linkage `distribution→rating≤4` holds by construction. `analyze_seed_video` attaches these 3 fields onto Gemini's craft JSON before returning (output shape unchanged → downstream unaffected). Residual dim variance is Gemini nondeterminism (temp=0 isn't fully deterministic), not anchoring. **#2 synthesis (`seed_insights`):** Instagram feeds its rubric via the dedicated `is_instagram` branch (full rated pool — `_is_content_driven` is NOT consulted); for TikTok, `_is_content_driven` keeps content/mixed only and discards distribution AND unclear, but TikTok-unclear means a thin-sample rating-5 (dormant — excluded from HIGH/LOW buckets regardless), so nothing teachable is lost. `distribution` requires a real reach floor (`DISTRIBUTION_MIN_VIEWS`=100k): only ≥100k-view + <2%-like videos are labeled `distribution` (reach carried weak content). A modest-reach (10k–100k) <2% video is `content`/3 instead — genuinely weak content that stays a teachable LOW example rather than being dropped by #2's filter. (`LIKE_RATE_MIN_VIEWS`=10k is the separate noise floor below which like-rate is meaningless → dormant 5/unclear.) Pre-change seeds keep old view-anchored ratings until re-harvested.
- `services/seed_harvest.py` — TikTok auto-harvest via tikwm. `NICHE_KEYWORDS` (50 niches × 3–4 keywords). `asyncio.gather + Semaphore(3)`. Dedupes via `vid:{video_id}` in notes.
- `services/instagram_harvest.py` — Instagram auto-harvest via HikerAPI (`HIKERAPI_KEY`). 100 req/month free tier: 2 keywords/niche × 50 niches = 100 calls. `asyncio.gather + Semaphore(3)`. Filters `media_type==2 && product_type=="clips"`. Dedupes via `ig:{media_pk}`.
- `services/seed_promote.py` — Background promotion of verified user videos into seed library. Idempotent via `promoted_seed_id`. Consent gate: minors never promote; `"ask"` parks (sets `pending_seed_consent`); `"yes"` proceeds.
- `services/seed_correction.py` — `audit_prediction(analysis_id)` background task. Text-only Gemini pass (no video) comparing the stored prediction (`scores_json`) to the real outcome (`actual_views/likes`). Writes `user_analyses.correction_json`. Guards: skips error/0-score rows, null likes, immature outcomes (`actual_views < MIN_VIEWS_FOR_CORRECTION` = 5000), and consent (`is_minor` or `seed_consent="no"`; **`"ask"`/`"yes"` proceed** — correction is invisible internal telemetry, no UI, so blocking `"ask"` adds no friction, only loses data). Recomputes + overwrites on refresh (like-rate matures); row-locked. De-confound rule lives in the prompt (rule out distribution before blaming content). Tags `mode` + `audited_at_views` + `audited_calibration_version` (Build #3 hole-2 guard) on each correction.
- `services/calibration.py` — Build #3. `generate_calibration_note(platform, niche)` rebuilds a note FROM SCRATCH (never stacks) from `correction_json` rows, filtered to safe-to-learn-from + thinking/deep + recent (≤120d) + NOT already-nudged (`audited_calibration_version==0`). Floors: ≥12 corrections (`MIN_CORRECTIONS`) or raises ValueError. Every dim adjustment clamped server-side: down ≤1.0, up ≤0.5 (tighter — selection bias). `load_calibration_note(db, platform, niche)` loads niche note → GLOBAL fallback, stamps non-zero `version`. Application gate lives in `gemini._calibration_applies` (high-confidence + sample≥12 + real directive). Inert until corrections accumulate + admin triggers generation.
- `services/niche_classifier.py` — Free-text → `{canonical, secondary, confidence, needs_confirmation}` via small Gemini call. `_match_canonical()` = exact + near-miss (e.g. "DIY"→"DIY & Crafts"). Real multi-niche: `secondary` (explicit pick canonicalized via `_match_canonical`, no Gemini) drives a promote-only weight MERGE in the grading prompt. #4 honesty: off-list/ambiguous/failure → `UNCATEGORIZED` sentinel (matches no insight/seed → generic dimension hierarchy, never a wrong niche) + `needs_confirmation` (rides in `scores_json`, exposed by `_to_out` for a frontend confirm prompt). Never blocks analysis. `seed_promote` skips promoting `UNCATEGORIZED`.
- `services/niche_weights.py` — Per-niche `NicheProfile` (critical/high/standard/low dims + context) → `get_dimension_hierarchy_block(niche, platform, secondary_niche="")`. **Real multi-niche merge (`_merge_promote`):** the PRIMARY niche stays the spine (seeds/insight/trend/calibration/`canonical_niche` all key on it — learning loop untouched); the SECONDARY can only RAISE a dim's tier, never lower one the primary set, primary wins conflicts, and a primary-LOW dim is immovable (prevents impossible scorecards e.g. ASMR+Comedy on `cut_frequency`). ≤3-critical cap preserved (primary keeps the slots). `get_blend_note()` = secondary-promotion addendum for the data-derived (insight) hierarchy path. **Emotional intent:** `NICHE_EMOTIONS` (50 niches, synced to `CANONICAL_NICHES`) + `get_emotional_target_block(niche, secondary)` → EMOTIONAL INTENT prompt block (primary feeling leads, secondary added) + the `emotional_analysis` output (`{target_emotions, achieved_score 0-10, what_lands, what_misses, how_to_amplify}`, rides in `scores_json`, no schema change; shown on improve page, locked for anon).
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

**Railway is on the FREE plan.** Deploys are limited to 1–2 per day max. Every backend deploy rebuilds the Docker image and costs credits. **30 deploys burned through Render's free tier** — don't repeat this pattern.

**NEVER deploy unless the user explicitly says "deploy" or "push to Railway".** Do not push to trigger a deploy as a convenience, to verify a fix, or as part of a task unless directly instructed.

**Rules:**
1. **Do not deploy without explicit instruction.** Always wait for the user to say so.
2. **Batch backend changes.** Never push a single-line backend fix. Accumulate multiple changes and push once.
3. **Test locally before every backend push.** Run `uvicorn main:app --reload` and manually verify the change works. A push that requires a follow-up fix = 2 deploys for 1 fix.
4. **Frontend deploys are free** (Vercel bandwidth is generous). The discipline applies to backend (`main` branch pushes that touch `backend/`).
5. **Schema changes + code changes = one push.** Don't push the schema change, verify, then push the code. Do both together.
6. **Never push to fix a typo or log statement.** Fix locally, bundle it into the next real change.

**Before any backend push, ask:** "Can I combine this with anything else that's pending?" If yes, wait.
