# AGENTS.md

Guidance for Codex when working in this repository. Keep this file and `CLAUDE.md` synchronized and keep this file under 200 lines.

## General behavior

- Reach 95% confidence before changing code. Ask focused follow-up questions only when repository context cannot resolve a material ambiguity.
- Preserve unrelated local changes. Never deploy, push, or trigger Railway without explicit user instruction.
- Update this file and `CLAUDE.md` whenever architecture or product contracts change.

## Product contract

CraftLint is an outcome-blind AI retention craft reviewer and post-experiment tracker. It is not a virality or retention predictor.

- The review is split across two models: Gemini describes the video (a perception/description pass — observations only, no scores), and Claude Sonnet 5 reasons over that description to assess six observable attention-retention craft dimensions: hook velocity, cut frequency, text scannability, curiosity gap, audio-visual sync, and ending strength (does the ending earn the finish — payoff, CTA, or a clean loop; internal key remains `loop_seamlessness` for data continuity). Gemini writes the observation (the evidence); Claude assigns the score — evidence precedes score across the model boundary.
- Dimension values are subjective AI assessments, not retention, engagement, reach, or causal measurements.
- Attention-risk maps are AI-estimated craft diagnostics by video section, not measured retention, watch time, or drop-off data.
- Niche selection is optional friction, not source of truth. When no user hint is supplied, CraftLint auto-detects rubric context from the video/caption and falls back to a broad craft rubric on low confidence.
- Do not produce an aggregate Viral Score, predicted views/likes, projected verdict, or performance promise.
- Recommendations are hypotheses for the creator's next controlled experiment. They must identify one change, what to hold constant, and what to observe.
- Keep AI critique separate from observed platform outcomes in code, storage, API contracts, and UX.
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
cd backend && PYTHONPATH=. python -m tools.score_distribution              # grader score spread + 5–7 compression warning
```

`backend/.env` and `frontend/.env.local` already exist locally. Railway is the backend host; Vercel hosts the frontend.

## Architecture

```text
Browser → Next.js (Vercel) → FastAPI (Railway) → Neon Postgres
                                               → Google Gemini (video perception / description pass)
                                               → Claude Sonnet 5 (per-video craft scoring + critique)
                                               → Claude Opus 4.8 (weekly admin-seed niche synthesis, configured-off)
                                               → TikWM · HikerAPI · RapidAPI (providers)
                                               → Stripe (billing) · Brevo (email) · Cloudflare R2 (uploads)
```

### Backend

Key models in `models.py`:

- `users`, `user_profiles`, `password_reset_tokens`, `email_verification_tokens`: identity, per-platform creator settings, age gate, password-reset/email-verification.
- `user_analyses`: uploaded review + full Gemini response. On a VERIFIED provider link fetch, `_sync_user_seed` promotes the (counts-blind) review into `seed_videos` as `source="user"` — rating derived from real counts via `score_outcome`, idempotent through `promoted_seed_id`, gated off for minors and `seed_consent="no"`. This is how real outcomes (including Instagram, which has no admin seeds) start feeding niche synthesis. Admin **User Seeds** tab surfaces these; the curated Seed Library excludes `source="user"`.
- `analysis_artifacts`: exact SHA-256 + creator/post identity for dedup.
- `outcome_snapshots`: immutable public-metric observations (capture time, post age, maturity horizon, provenance, integrity flags).
- `outcome_collection_jobs`: durable maturity-window jobs, bounded retry and missed-window handling; driven by `services/outcome_collection.py`.
- `usage_events`: latency/bytes/tokens/success + optional verified cost (NULL until real pricing is configured). Durable ledger behind collector-health/fetch-reliability.
- `trend_summaries`, `niche_insights`: synthesized scoring-intelligence, weekly-regenerated by `services/niche_synthesis.py` from the seed pool (also admin-manually-triggerable), injected into the Claude scoring prompt when `NICHE_SYNTHESIS_ENABLED` is on — never user-facing.
- `rate_limit_hits`, `pending_uploads`: shared-DB backing for the brute-force/spam throttle (`services/throttle.py`) and the presigned-upload ownership store, so limits/keys hold across workers/replicas. Pruning a stale (TTL-expired, never-claimed) `pending_uploads` row also deletes its R2 object — an abandoned presigned upload must not leave an orphaned video sitting in R2 forever, since the Privacy Policy promises videos aren't retained.
- `seed_videos`, `calibration_notes`: legacy research + AI-calibration infrastructure. Calibration is OFF by default (`SURGE_CALIBRATION_ENABLED`) — never feed these into a live craft review while disabled.

Key services and routes:

- `routers/analyze.py`: upload/review, provider links, `GET /api/analyses/{id}/outcomes`; promotes to the seed pool via `_sync_user_seed` on a VERIFIED link.
- `services/gemini.py`: orchestrates the two-model review and owns the DETERMINISTIC video perception/description pass — Gemini `gemini-2.5-flash`, temperature=0 + fixed seed, video sampled at 4fps with `media_resolution: low` (≈264 tokens/sec vs. ≈258 at Gemini's 1fps/default-res default, quadrupling temporal sampling for cut_frequency/hook_velocity on fast-cut content at roughly the same cost). This pass OBSERVES and DESCRIBES only — no scores, no advice — emitting per-dimension observations, section observations, and an emotional read; it auto-detects rubric context when no niche hint is given. `analyze_video` then resolves the niche, calls the Claude scoring pass, and merges/validates. The pinned perception makes the DESCRIPTION reproduce run-to-run; an unusable description short-circuits to an error dict (never spends the Claude call). Injection-resistant system/data separation.
- `services/claude_scoring.py`: the per-video SCORING pass — Claude Sonnet 5 (`claude-sonnet-5`, adaptive thinking, `output_config.format` structured outputs matching what `_validate_analysis_result` expects). Effort is TIERED by the caller (`routers/analyze.py` maps `is_pro(user)` → `"high"`, free/guest → `"medium"`; `score_from_perception` clamps any unrecognized value to the medium default) — effort drives thinking depth and is the main scoring-cost lever. Reasons over Gemini's description and produces the six scores (`not_applicable` allowed for cut_frequency/text_scannability; `craft_review_version` 5), the section-level attention-risk map, critique, and next experiment — evidence-then-score across the model boundary (Gemini writes the observation, Claude assigns the number). Injects the niche dimension-priority hierarchy, emotional-target hint, and the gated `load_niche_synthesis_block` as ordering context only, never to change a score — the live review is otherwise blind to prior individual outcomes, seed labels, channel history. Sonnet 5 rejects sampling params, so this pass is NOT temperature-pinnable (bounded reproducibility). ANY failure (rate limit/overload/5xx, refusal, truncation, empty/malformed JSON, missing key) returns `(None, message)` → `analyze_video` returns an error dict (`status="error"`), NEVER a fabricated scorecard — there are no perception scores to degrade to. Records its own `video_craft_scoring` usage event (provider `anthropic`).
- `services/niche_weights.py`, `niche_classifier.py`, `channel_profile.py`: build the static injected scoring blocks (niche dimension hierarchy, `Uncategorized` → neutral weights never a guess, Deep-mode creator-history summary). Frame history honestly so the grader never mistakes its own past opinions for external validation.
- `services/seed_statistics.py`: code-first seed-pool statistics extending `tools/craft_correlation.py`'s methodology (Pearson r, Fisher CI, sample-size-justified reportability) to the seed pool — per-dimension correlation against a seed's code-derived `rating`, inter-dimension collinearity, and a deterministic CRITICAL/HIGH/STANDARD/LOW tier from measured effect size (Cohen's convention, capped at ≤2 CRITICAL / ≥1 LOW). No LLM call in this module.
- `services/seed_insights.py`, `trend_insights.py`: narrate `seed_statistics.py`'s already-validated numbers into English via Claude Opus 4.8 (all-time niche patterns, recent-vs-established trend delta) — the model narrates only the numbers it's handed, never a raw seed dump, per CLAUDE.md's correlation/causation rules. Also callable manually from `routers/admin.py`.
- `services/claude_client.py`: thin Anthropic wrapper (`tracked_claude_message`, `claude-opus-4-8`, adaptive thinking) — the Claude-side counterpart to `services/telemetry.py`'s Gemini wrapper. Offline/admin-triggered only, never in the live per-video request path.
- `services/niche_synthesis.py`: orchestrates the weekly niche+trend synthesis across every `(platform, niche)` with enough seed data, upserts `niche_insights`/`trend_summaries`, and exposes `load_niche_synthesis_block()` for grade-time injection. Gated by `NICHE_SYNTHESIS_ENABLED` (default OFF) at both the scheduler entry point and the grade-time read; admin manual-trigger generation (`routers/admin.py`) works regardless of the flag.
- `services/outcome_collection.py`: due-job collection, bounded retry (3 attempts), row-locked finalization (no double-count), late jobs marked `missed`, `collector_health()` exposed at `GET /health/collectors`.
- `services/scheduler.py`: in-process jobs — daily 06:00 UTC `collect_due_outcomes()` then `summarize_run()` (ERROR-logs a high-failure run), and weekly Monday 07:00 UTC `run_weekly_niche_synthesis()` (no-op unless `NICHE_SYNTHESIS_ENABLED`).
- `services/outcomes.py`: computes post age, assigns maturity windows, stores immutable snapshots.
- `services/clock.py`: single source of truth for the clock — `utc_now_naive()`. Never mix aware/naive datetimes or call deprecated `datetime.utcnow()`.
- `services/tiktok_fetch.py` / `instagram_fetch.py`: untrusted provider adapters. Missing required counts fail closed; optional fields stay NULL.
- `services/telemetry.py` / `services/economics.py`: provider/model telemetry and the admin operations report. Do not claim cost or margin until pricing and payloads are verified.
- `services/craft_insights.py`: shared dimension constants and score-parsing helper (`DIMENSIONS`, `DIMENSION_LABELS`, `_craft_scores`, verified-source list, view-rate floor) read by `tools/craft_correlation.py`, `tools/score_distribution.py`, and `services/seed_statistics.py`. The user-facing "Craft vs. Your Results" insights tab that used to live on top of this was removed (low usage, gated too often on sparse data); this module now exists only to keep those offline tools' dimension sets and thresholds consistent.
- `tools/craft_correlation.py`: offline, read-only, cross-user craft↔outcome correlation (Pearson r + 95% Fisher CI, Spearman rho, n, naive baselines, collinearity). Must show real signal before the calibration path is ever enabled. Never in the request path.
- `auth.py`: JWT helpers and the single canonical `is_minor()` / `is_pro()` / `is_comp()`. `is_pro` reads `users.subscription_status` OR the comp allowlist.
- `services/stripe_billing.py` + `routers/billing.py`: adult-only hosted Checkout/portal sessions + a SIGNATURE-VERIFIED, target-price-validated webhook that is the ONLY writer of subscription state. The durable `stripe_webhook_events` ledger suppresses duplicate deliveries, every subscription event reconciles the customer's current Stripe state so out-of-order/old-subscription events cannot revoke a newer plan, and account deletion cancels Stripe first so it cannot orphan a still-charging subscription. Never trust the client or success URL for Pro status. Stripe `StripeObject` raises on `.get()` — use the `_g()` safe accessor.
- `services/rate_limit.py`: Pro = unlimited monthly, gated by a soft daily fair-use ceiling AND a rolling 5-hour cost-window cap (`services/cost_window.py`); free = 3 analyses/calendar-month (UTC) + earn-by-linking bonus. Failed (`status="error"`) analyses never consume the allowance.
- `services/cost_window.py`: Pro-only rolling 5-hour spend cap, budgeted in estimated dollars (`usage_events.estimated_cost_micros`), never raw tokens — not stacked on the free tier's monthly count. Continuous trailing-window (recomputed sum over the trailing 5h, joined via `user_analyses.user_id` since `usage_events` has no `user_id` column), not a discrete session bucket — stateless, read-only, no new table. Default budget $1.00/window, a launch-time guess (no real spend data yet), env-tunable via `PRO_COST_WINDOW_BUDGET_USD` without a redeploy. Read-only gate, not a locked reservation — a burst of concurrent requests can admit past the cap before their cost is written (same tradeoff `services/throttle.py` documents for its own sliding window).
- `routers/settings.py`: account deletion removes analyses/artifacts/snapshots/usage events in FK-safe order.
- `routers/admin.py`: password-gated (`ADMIN_PASSWORD`) — outcome collection, ops/cost reports, seed/harvest/trend management, the user-seed console, calibration/insight generation. Never exposed to normal users.

TikWM, HikerAPI, and RapidAPI are operational dependencies with rate-limit, schema-drift, availability, and cost risk. Provider fields without local real-payload verification: document as "not runtime-verified."

New tables come from `create_all`. Existing-column additions need model updates plus SQLite/Postgres additive shims in `main.py` (`_ensure_columns`).

### Frontend

Design system is **"Noir"**: true black/white neutrals, one pink accent used sparingly (`--color-accent` pink = act/CTAs/live signals; `--color-accent-2` ice = inform/insights/secondary), display face Schibsted Grotesk. **Never purple/gradient soup, never the generic centered-hero-with-pill-buttons layout — CraftLint must not look "AI-generated."** Two first-class themes (dark default `#0A0A0B`/pink `#FF4D8D`, light paper-white/raspberry `#D6246E`) via `data-theme` on `<html>`, flipped by `components/ThemeToggle.tsx` and restored pre-paint with no flash. All colors are CSS tokens in `app/globals.css` (`:root` = dark, `[data-theme="light"]` overrides); verify every visual change in BOTH themes at both desktop and mobile widths. Platform brand colors (TikTok glitch `#25F4EE`/`#FE2C55`, Instagram gradient) live in a separate `@layer utilities` layer and animate HOVER-ONLY on the wordmark — never idle/looping. Verdict labels/colors come from `lib/verdicts.ts`.

- `app/page.tsx`, `app/results/[id]/page.tsx`, `app/results/[id]/improve/page.tsx`: the craft review flow — six dimensions, attention-risk map, explicit evidence notice, next experiment, and a separate 24h/7d/30d outcome timeline. No projected performance anywhere.
- `app/projects/page.tsx`: unlinked posts sorted first then newest-first; mixed-age latest counts are not comparisons.
- `components/FeedbackModal.tsx`: manual unverified observations; provider fetches are preferred where available.
- `components/ProfileNudgeModal.tsx`: one-time post-signup nudge, shown once on first dashboard arrival.
- `lib/api.ts`: typed review/outcome contracts plus local anonymous-analysis claim-token storage.
- `components/Skeleton.tsx` and shared motion rules in `app/globals.css`: reusable loading/busy states and reduced-motion behavior.
- `components/NichePicker.tsx`: optional rubric hint picker — never make it required in the main upload flow.

Next.js 15 App Router requires `"use client"` for hooks such as `useParams`, `useSearchParams`, and auth state. PWA assets are under `frontend/public`.

## Security, privacy, and reliability

- Rate checks run before Gemini calls. Re-raise Gemini 429/403 so callers receive 503 rather than a fabricated report. The Claude scoring pass handles its own failures internally — any failure returns an error dict (`status="error"`), never a fabricated scorecard, since scores live there now and there is nothing to degrade to.
- Resolve client IPs for rate-limit / brute-force keys ONLY via `services.throttle.client_ip` (honours `TRUSTED_PROXY_HOPS`). Never key a throttle on the leftmost `X-Forwarded-For` entry — it is caller-supplied and lets an attacker rotate the header to mint unlimited buckets.
- `services.throttle.check_rate` is DB-backed (the `rate_limit_hits` table) and async — call it as `await check_rate(db, key, max_hits, window_seconds)`; it commits the hit immediately so it stays durable and shared across workers, and every call site invokes it before any other write in the handler. The `WEB_CONCURRENCY=1` pin is no longer forced by in-memory state, but before raising it keep `workers * (pool_size + max_overflow)` (see `database.py`) under Neon's `max_connections`. For serious scale, move the throttle to Redis to keep this load off the primary DB.
- A Gemini failure that returns an error dict (not a 429/403 raise) — or ANY Claude scoring failure — is stored with `status="error"`, so it is excluded from the upload limiter and the UI shows a failure screen instead of an all-zero scorecard.
- Outcome collection is durable and self-reporting: jobs retry up to 3 times, late jobs are marked `missed` (never mislabeled as 24h/7d/30d), finalization is row-locked so a concurrent run cannot double-count, and `GET /health/collectors` reports ok/degraded/failing/idle from durable tables so a silently failing collector cannot look idle.
- The AI-calibration path (correction audit → calibration note → grade-time nudge) is OFF by default and gated at every entry point by `SURGE_CALIBRATION_ENABLED`; while disabled, no stored note can reach the grader. Do not enable it without the drift metric (`tools/craft_correlation.py`) in place — the risk is runaway self-reinforcement and selection-bias inflation, not accuracy.
- The admin-seed niche/trend synthesis path is OFF by default and gated by `NICHE_SYNTHESIS_ENABLED` at both the weekly scheduler entry point and the grade-time read; while disabled, no synthesized block can reach the grader. Its statistics are computed in code first (`services/seed_statistics.py`, extending `tools/craft_correlation.py`'s methodology) — the narrating LLM (Claude Opus 4.8) only restates already-validated numbers and is never handed the raw seed pool, so it cannot freeform "find patterns." Lower risk than the calibration path (an independent seed-pool ground truth, not the grader auditing its own past predictions), which is why it doesn't require the same `craft_correlation.py` pre-signal gate before enabling. Note: only the READ is flag-gated — admin manual generation (`routers/admin.py`'s `/insights/generate` and `/trends/generate`) always works so an operator can preview quality before deciding to flip the switch. This means whatever is already sitting in `niche_insights`/`trend_summaries` (including rows generated while the flag was off) becomes live-grading input the moment `NICHE_SYNTHESIS_ENABLED` flips on — review or regenerate current content before enabling, don't assume a fresh state.
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
- `ANTHROPIC_API_KEY`: **required for the core grading path** — `services/claude_scoring.py` (Claude Sonnet 5) is the per-video scoring pass, so without the key EVERY analysis fails closed after the Gemini description pass (`status="error"`, no scorecard, no credit consumed). It ALSO powers the weekly admin-seed niche/trend synthesis (`services/claude_client.py`, `services/niche_synthesis.py`), which is configured-off without it (synthesis generation raises a clear "not configured" error that admin endpoints and the scheduler catch and skip, never crashing).
- `NICHE_SYNTHESIS_ENABLED` (default OFF): master switch for the weekly scheduler run AND the grade-time injection read (`load_niche_synthesis_block`, called in `services/gemini.py` and threaded into the Claude scoring prompt). Read at call time, same pattern as `SURGE_CALIBRATION_ENABLED`. Admin manual insight/trend generation works regardless of this flag; only the automatic weekly run and live-grading injection are gated.
- `TRUSTED_PROXY_HOPS` (default 1): trusted reverse-proxy hops in front of the app, used to read the real client IP from `X-Forwarded-For` for rate limiting. 1 is correct for Railway's single edge proxy; only raise it if you add more trusted proxies.
- `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET` (CraftLint Pro billing): all optional — without them the `/api/billing/*` routes return 503 and the app is unaffected (configured-off, like Google sign-in). The publishable key is not needed (Stripe-hosted Checkout). See `STRIPE_SETUP.md`.
- `COMP_PRO_EMAILS` (optional): comma-separated, case-insensitive allowlist of emails granted Pro (unlimited) for free with no Stripe. Operator-only (server-side); used for owner/tester comp accounts. `auth.is_comp()` / `is_pro()`.
- `PRO_COST_WINDOW_BUDGET_USD` (optional, default `1.00`): rolling 5-hour Pro cost-window budget in USD (`services/cost_window.py`). A non-positive or unparseable value falls back to the default rather than locking out all of Pro.

## Legal documents

The Terms of Service lives at `frontend/app/terms/page.tsx`. The site URL is env-driven: every consumer (ToS, metadata, OG image, robots, sitemap) reads `SITE_URL`/`SITE_HOST` from `frontend/lib/site.ts`, which falls back to the Vercel URL. When a custom domain goes live, set `NEXT_PUBLIC_SITE_URL` in Vercel (and `FRONTEND_URL`/`ALLOWED_ORIGINS` in Railway) — no code edits needed.

## Deploy discipline

Railway is on a limited free plan. Backend deploys must be batched.

1. Do not deploy or push without explicit instruction.
2. Run backend tests/compile and frontend typecheck/build locally before a push.
3. Combine schema and backend code in one verified push.
4. Do not spend a backend deploy on a typo or log-only change.
5. Before any backend push, ask: "Can I combine this with anything else that's pending?"
