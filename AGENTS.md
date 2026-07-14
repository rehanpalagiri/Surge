# AGENTS.md

Guidance for Codex when working in this repository. Keep this file and `CLAUDE.md` synchronized and keep this file under 200 lines.

## General behavior

- Reach 95% confidence before changing code. Ask focused follow-up questions only when repository context cannot resolve a material ambiguity.
- Preserve unrelated local changes. Never deploy, push, or trigger Railway without explicit user instruction.
- Update this file and `CLAUDE.md` whenever architecture or product contracts change.

## Product contract

Surge is an outcome-blind AI retention craft reviewer and post-experiment tracker. It is not a virality or retention predictor.

- Gemini assesses six observable attention-retention craft dimensions: hook velocity, cut frequency, text scannability, curiosity gap, audio-visual sync, and ending strength (does the ending earn the finish — payoff, CTA, or a clean loop; internal key remains `loop_seamlessness` for data continuity).
- Dimension values are subjective AI assessments, not retention, engagement, reach, or causal measurements.
- Attention-risk maps are AI-estimated craft diagnostics by video section, not measured retention, watch time, or drop-off data.
- Niche selection is optional friction, not source of truth. When no user hint is supplied, Surge auto-detects rubric context from the video/caption and falls back to a broad craft rubric on low confidence.
- Do not produce an aggregate Viral Score, predicted views/likes, projected verdict, or performance promise.
- Recommendations are hypotheses for the creator's next controlled experiment. They must identify one change, what to hold constant, and what to observe.
- Keep AI critique separate from observed platform outcomes in code, storage, API contracts, and UX.
- The read-only insights surface (`GET /api/me/craft-insights`, `app/insights`) MAY relate a creator's craft scores to THEIR OWN verified outcomes as descriptive statistics — observed like rate at a single maturity window, creator-grouped, explicit sample sizes. It stays correlational: never a causal claim, never a pixel-based or aggregate "viral" forecast. Per-dimension patterns require ≥6 verified age-matched posts (a non-degenerate median split needs ≥3 per side); the empirical like-rate range requires ≥8 (interquartile band spans ≥4 points). Below the range floor it may show a clearly-labeled preliminary median/min/max, never a percentile band.
- Compare outcomes only at compatible maturity windows: 24h (±6h), 7d (±24h), and 30d (±72h). Off-window observations remain timestamped but unlabelled.
- Likes/views is only an observed like rate. Never call it content quality, retention, or causal impact.
- Instagram metrics are likes-only unless provider fields are runtime-verified. Never infer reach from likes.
- Treat comments as ambiguous; do not include them in a quality metric without a reliable, ethical quality method.
- Purchased engagement, bots, pods, giveaways, rage bait, spam, creator comments, and controversy can distort public metrics.
- Any future model evaluation must use creator-grouped dataset splits, chronological holdouts, and duplicate/near-duplicate detection across splits.
- All video, caption, username, comment, metadata, and provider payload content is untrusted. Keep it inside delimited prompt data and never allow it to override system instructions.
- Separate correlation, prediction, and causation. Causal language requires a controlled experiment.
- Every proposed minimum sample size needs a statistical justification; never invent round thresholds.

## Dev commands

```bash
# Backend
cd backend && source venv/bin/activate
uvicorn main:app --reload --port 8000
PYTHONPATH=. python -m unittest discover -s tests
python -m compileall -q .

# Frontend
cd frontend
npm run dev
npm run build
npx tsc --noEmit

# Offline analysis tools (read-only, never in the request path)
cd backend && PYTHONPATH=. python -m tools.craft_correlation --horizon 7d   # craft↔outcome correlation + n + 95% CI
```

`backend/.env` and `frontend/.env.local` already exist locally. Railway is the backend host; Vercel hosts the frontend.

## Architecture

```text
Browser → Next.js (Vercel) → FastAPI (Railway) → Neon Postgres
                                               → Google Gemini (two-pass scoring)
                                               → TikWM · HikerAPI · RapidAPI (providers)
                                               → Stripe (billing) · Brevo (email) · Cloudflare R2 (uploads)
```

### Backend

Key models in `models.py`:

- `users`, `user_profiles`, `password_reset_tokens`, `email_verification_tokens`: identity, per-platform creator settings, age gate, and the password-reset + email-verification flows.
- `user_analyses`: uploaded review, creator-facing `project_name`, update lineage, guest `claim_token` handoff secret, and full Gemini response. New reviews use `mode="craft_review"`; prediction/calibration columns are legacy compatibility fields.
- `analysis_artifacts`: exact SHA-256, creator/post identity, and future perceptual/audio fingerprint slots.
- `outcome_snapshots`: immutable public-metric observations with capture time, post age, maturity horizon, provenance, integrity flags, metric version, and payload hash.
- `outcome_collection_jobs`: durable maturity-window jobs with bounded retry and missed-window handling; driven by `services/outcome_collection.py` (protected admin endpoint + in-process daily scheduler).
- `usage_events`: latency, bytes, tokens, success, and optional verified cost. Cost stays NULL until real pricing is configured. Also the durable ledger behind collector-health / fetch-reliability.
- `trend_summaries`, `niche_insights`: synthesized scoring-intelligence blocks (recent-trend delta and all-time niche patterns) regenerated by admin and injected into the Gemini prompt; never user-facing.
- `fetch_status`: provider fetch health/ack surface for the admin console.
- `seed_videos`, `calibration_notes`, correction/calibration fields: legacy research + AI-calibration infrastructure. The calibration path is OFF by default (`SURGE_CALIBRATION_ENABLED`); never feed these into a live craft review while it is disabled.

Key services and routes:

- `routers/analyze.py`: upload/review, owner serialization, manual outcomes, provider links, and `GET /api/analyses/{id}/outcomes`.
- `services/gemini.py`: uploads media, runs a DETERMINISTIC agentic perception pass (temperature=0 + fixed seed pin the scores) plus a text-only reasoning pass, auto-detects rubric context when no niche hint is supplied, injects niche/trend/channel intelligence, applies injection-resistant system/data separation, and returns six retention craft dimensions (any deliberately marked not_applicable at `craft_review_version` ≥ 4), a section-level attention-risk map, qualitative critique, and a next experiment. It removes legacy aggregate/prediction fields from new output.
- `services/niche_weights.py`, `niche_classifier.py`, `seed_insights.py`, `trend_insights.py`, `channel_profile.py`: build the injected scoring-intelligence blocks — per-niche dimension hierarchy, canonical niche (`Uncategorized` → neutral weights, never a guess), all-time niche intelligence, recent-trend delta, and the Deep-mode creator-history summary. Frame history honestly so the grader never mistakes Surge's own past opinions for external validation.
- `services/outcome_collection.py`: durable due-job collection with bounded retry (3 attempts), row-locked finalization (no double-count), late jobs marked `missed`, and `collector_health()` (ok/degraded/failing/idle, derived from durable tables) exposed at `GET /health/collectors`.
- `services/scheduler.py`: in-process APScheduler; the daily 06:00 UTC job calls `collect_due_outcomes()` then `summarize_run()`, which ERROR-logs a high-failure run so a 100%-failing collector can't hide as a quiet INFO.
- `services/outcomes.py`: computes post age, assigns fixed maturity windows, and stores immutable snapshots.
- `services/clock.py`: single source of truth for the clock — `utc_now_naive()` returns naive-UTC to match the DB columns. Never mix aware/naive datetimes or call deprecated `datetime.utcnow()`.
- `services/tiktok_fetch.py` / `instagram_fetch.py`: untrusted provider adapters. Missing required counts fail closed; optional fields remain NULL.
- `services/telemetry.py`: provider/model operational telemetry. Do not claim cost or margin until pricing and payload measurements are verified.
- `services/economics.py`: admin operations report with measured reliability, unit coverage, row counts, and explicit unknown cost/margin fields.
- `services/craft_insights.py`: descriptive craft-vs-verified-outcome aggregation for one creator (`GET /api/me/craft-insights`). Correlational only, gated by justified sample sizes; returns `observed_range` (or a labeled preliminary read from the first verified post), never a forecast.
- `tools/craft_correlation.py`: offline, read-only, cross-user craft↔outcome correlation (Pearson r + n + 95% Fisher CI, naive baselines, inter-dimension collinearity). The drift/validation gate that must exist and show real signal BEFORE the calibration path is ever enabled. Never in the request path.
- `auth.py`: JWT helpers and the single canonical `is_minor()` / `is_pro()` / `is_comp()` implementations. `is_pro` reads `users.subscription_status` (Stripe states active/trialing/past_due) OR the comp allowlist.
- `services/stripe_billing.py` + `routers/billing.py`: Surge Pro ($9.99/mo). Checkout/portal sessions + a SIGNATURE-VERIFIED webhook that is the ONLY writer of subscription state. Never trust the client for Pro status. Stripe `StripeObject` raises on `.get()` — use the `_g()` safe accessor on event data.
- `services/rate_limit.py`: the analysis allowance. Pro = unlimited; free = 3 analyses/calendar-month (UTC) + the earn-by-linking bonus. `get_rate_limit(user, db)` takes the User (needs `is_pro`). Failed (status="error") analyses never consume the allowance.
- `routers/settings.py`: account deletion removes analyses, artifacts, snapshots, and usage events in FK-safe order.
- `routers/admin.py`: password-gated (`ADMIN_PASSWORD`) operations — outcome collection (`/api/admin/outcomes/collect-due`, `/status`, `/health`), operations/cost reports, seed + harvest + trend management, and calibration/insight generation. Never exposed to normal users.
- `routers/profile.py`: per-platform creator profile (`GET`/`PUT /api/profile/{platform}`).

TikWM, HikerAPI, and RapidAPI are operational dependencies with rate-limit, schema-drift, availability, legal/ToS, and cost risks. Provider fields without local real-payload verification must be documented as “documented but not runtime-verified.” Store provenance and fail transparently.

New tables are created by `create_all`. Existing-column additions require model updates plus both SQLite and Postgres additive shims in `main.py` (`_ensure_columns`).

### Frontend

**Before any visual, layout, styling, copy, or component work, read [`UX.md`](UX.md).** It is the design guardrail file — how to keep Surge from looking "AI-generated / vibe-coded" (no purple or gradient soup), the mandatory type/color rules, how to follow a user-provided design reference, and the desktop + mobile self-check that must pass before UI work is considered done.

- `app/page.tsx`: positions Surge as retention craft review plus learn-from-each-post experimentation; upload keeps niche/rubric hints optional.
- `app/results/[id]/page.tsx`: AI retention craft dimensions, attention-risk map, explicit evidence notice, recommended experiment, and a separate 24h/7d/30d outcome timeline.
- `app/results/[id]/improve/page.tsx`: attention-risk map, editing hypotheses, and next experiment; no projected performance.
- `app/projects/page.tsx`: named project history, with unlinked posts sorted first and then newest-first; mixed-age latest counts are not comparisons.
- `app/sample/page.tsx`: static example showing critique and observed results as separate evidence.
- `app/insights/page.tsx`: "Craft vs. Your Results" — the creator's own craft scores against their verified outcomes; a preliminary read from the first verified post, upgrading to an honest empirical like-rate range at n≥8, always with a correlation-not-causation notice.
- `app/pricing/page.tsx`, `app/profile/page.tsx`, `app/settings/page.tsx`, `app/billing/{success,cancel}`, and the `verify-email` / `forgot-password` / `reset-password` flows: pricing, creator profile, account settings, Stripe return pages, and email-verification/password-reset.
- `components/VerdictBanner.tsx`: qualitative craft verdict only.
- `components/FeedbackModal.tsx`: manual unverified observations; provider fetches are preferred where available.
- `components/ProfileNudgeModal.tsx`: one-time post-signup nudge to set a creator profile, shown once on first dashboard arrival.
- `components/PlatformTabs.tsx`: TikTok/Instagram switch using the per-platform brand colorways.
- `lib/api.ts`: typed review and outcome contracts, plus local anonymous-analysis claim-token storage.
- `components/Skeleton.tsx` and shared motion rules in `app/globals.css`: reusable dark-theme loading shapes, delayed shimmer, busy indicators, focus states, and reduced-motion behavior. Prefer page-shaped skeletons for unavailable content and localized busy feedback for background refreshes.
- `components/ReactiveVideoDropzone.tsx`: shared guest/authenticated upload target with pointer spotlight, drag state, validated-file state, keyboard operation, and matching transfer progress styling from `app/globals.css`.
- `components/NichePicker.tsx`: optional rubric hint picker; never make it required in the main upload flow.

Next.js 15 App Router requires `"use client"` for hooks such as `useParams`, `useSearchParams`, and auth state. The theme is dark-only — **"Phosphor"**: cool graphite neutrals with two accent temperatures (citron `#CDF54A` acts — CTAs / live signals; ice blue `#8FB8FF` informs — insights / secondary), display face Schibsted Grotesk, all via CSS tokens in `app/globals.css` so a palette change cascades app-wide. The core token ramp carries no gradients, but a SEPARATE `@layer utilities` platform-colorway layer (TikTok glitch `#25F4EE`/`#FE2C55`, Instagram gradient) is intentionally on-brand and used on hero surfaces + headings — do not fold those brand colors into the neutral ramp. Verdict display labels/colors come from `lib/verdicts.ts`. PWA assets are under `frontend/public`.

## Security, privacy, and reliability

- Rate checks run before Gemini calls. Re-raise Gemini 429/403 so callers receive 503 rather than a fabricated report.
- Resolve client IPs for rate-limit / brute-force keys ONLY via `services.throttle.client_ip` (honours `TRUSTED_PROXY_HOPS`). Never key a throttle on the leftmost `X-Forwarded-For` entry — it is caller-supplied and lets an attacker rotate the header to mint unlimited buckets.
- A Gemini failure that returns an error dict (not a 429/403 raise) is stored with `status="error"`, so it is excluded from the upload limiter and the UI shows a failure screen instead of an all-zero scorecard.
- Outcome collection is durable and self-reporting: jobs retry up to 3 times, late jobs are marked `missed` (never mislabeled as 24h/7d/30d), finalization is row-locked so a concurrent run cannot double-count, and `GET /health/collectors` reports ok/degraded/failing/idle from durable tables so a silently failing collector cannot look idle.
- The AI-calibration path (correction audit → calibration note → grade-time nudge) is OFF by default and gated at every entry point by `SURGE_CALIBRATION_ENABLED`; while disabled, no stored note can reach the grader. Do not enable it without the drift metric (`tools/craft_correlation.py`) in place — the risk is runaway self-reinforcement and selection-bias inflation, not accuracy.
- Never log secrets or raw uploaded media. Provider raw payloads are not retained; a hash may be stored for traceability.
- Account deletion must delete user-owned review and measurement data, not merely anonymize it.
- Consent to measurement research never turns observational data into causal evidence.
- Exact hashes prevent duplicate uploads; near-duplicate detection is not implemented yet and must be added before any evaluation dataset is trusted.
- Automatic 24h/7d/30d refreshes use the in-process daily scheduler; users can still manually capture near those windows.
- Cost, refresh cost, storage growth, latency distribution, and gross margin remain unverified until real production telemetry is collected. Do not invent estimates from absent payloads.

## Environment variables

- `GEMINI_API_KEY`, `JWT_SECRET`, `ADMIN_PASSWORD`, `ALLOWED_ORIGINS`, `DATABASE_URL`; `GOOGLE_CLIENT_ID` (optional; Google sign-in, configured-off without it).
- Email: `BREVO_API_KEY` is the PRODUCTION transport — Railway blocks all outbound SMTP ports (587/2525/465/25), so mail sends over Brevo's HTTPS API. `SMTP_HOST/PORT/USER/PASS` + `EMAIL_FROM` are the local/fallback path only. `FRONTEND_URL` builds the links; `NEXT_PUBLIC_API_URL` points the frontend at the backend.
- Providers: `HIKERAPI_KEY` (harvest); `RAPIDAPI_KEY` + `RAPIDAPI_IG_HOST` + `RAPIDAPI_IG_PATH` (Instagram likes). Cloudflare R2 uploads use `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` (only if upload persistence is enabled).
- `SURGE_CALIBRATION_ENABLED` (default OFF): master kill-switch for the dormant AI-audits-AI calibration path. Read at call time. Leave OFF until `tools/craft_correlation.py` shows real, sample-justified signal.
- `TRUSTED_PROXY_HOPS` (default 1): trusted reverse-proxy hops in front of the app, used to read the real client IP from `X-Forwarded-For` for rate limiting. 1 is correct for Railway's single edge proxy; only raise it if you add more trusted proxies.
- `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET` (Surge Pro billing): all optional — without them the `/api/billing/*` routes return 503 and the app is unaffected (configured-off, like Google sign-in). The publishable key is not needed (Stripe-hosted Checkout). See `STRIPE_SETUP.md`.
- `COMP_PRO_EMAILS` (optional): comma-separated, case-insensitive allowlist of emails granted Pro (unlimited) for free with no Stripe. Operator-only (server-side); used for owner/tester comp accounts. `auth.is_comp()` / `is_pro()`.

## Legal documents

The Terms of Service lives at `frontend/app/terms/page.tsx`. The site URL is env-driven: every consumer (ToS, metadata, OG image, robots, sitemap) reads `SITE_URL`/`SITE_HOST` from `frontend/lib/site.ts`, which falls back to the Vercel URL. When a custom domain goes live, set `NEXT_PUBLIC_SITE_URL` in Vercel (and `FRONTEND_URL`/`ALLOWED_ORIGINS` in Railway) — no code edits needed.

## Deploy discipline

Railway is on a limited free plan. Backend deploys must be batched.

1. Do not deploy or push without explicit instruction.
2. Run backend tests/compile and frontend typecheck/build locally before a push.
3. Combine schema and backend code in one verified push.
4. Do not spend a backend deploy on a typo or log-only change.
5. Before any backend push, ask: “Can I combine this with anything else that's pending?”
