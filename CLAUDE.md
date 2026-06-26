# CLAUDE.md

This file mirrors `AGENTS.md`. Keep both synchronized when repository guidance changes.

## General behavior

- Reach 95% confidence before changing code. Ask focused follow-up questions only when repository context cannot resolve a material ambiguity.
- Preserve unrelated local changes. Never deploy, push, or trigger Railway without explicit user instruction.
- Update this file and `AGENTS.md` whenever architecture or product contracts change.

## Product contract

Surge is an outcome-blind AI craft reviewer and post-experiment tracker. It is not a virality predictor.

- Gemini assesses six observable craft dimensions: hook velocity, cut frequency, text scannability, curiosity gap, audio-visual sync, and loop seamlessness.
- Dimension values are subjective AI assessments, not retention, engagement, reach, or causal measurements.
- Do not produce an aggregate Viral Score, predicted views/likes, projected verdict, or performance promise.
- Recommendations are hypotheses for the creator's next controlled experiment. They must identify one change, what to hold constant, and what to observe.
- Keep AI critique separate from observed platform outcomes in code, storage, API contracts, and UX.
- The read-only insights surface (`GET /api/me/craft-insights`, `app/insights`) MAY relate a creator's craft scores to THEIR OWN verified outcomes as descriptive statistics — observed like rate at a single maturity window, creator-grouped, explicit sample sizes. It stays correlational: never a causal claim, never a pixel-based or aggregate "viral" forecast. Per-dimension patterns require ≥6 verified age-matched posts (a non-degenerate median split needs ≥3 per side); the empirical like-rate range requires ≥8 (interquartile band spans ≥4 points).
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
```

`backend/.env` and `frontend/.env.local` already exist locally. Railway is the backend host; Vercel hosts the frontend.

## Architecture

```text
Browser → Next.js (Vercel) → FastAPI (Railway) → Neon Postgres
                                               → Google Gemini
                                               → TikWM / HikerAPI
```

### Backend

Key models in `models.py`:

- `users`, `user_profiles`, `password_reset_tokens`: identity, settings, age gate, and reset flow.
- `user_analyses`: uploaded review, creator-facing `project_name`, update lineage, and full Gemini response. New reviews use `mode="craft_review"`; prediction/calibration columns are legacy compatibility fields.
- `analysis_artifacts`: exact SHA-256, creator/post identity, and future perceptual/audio fingerprint slots.
- `outcome_snapshots`: immutable public-metric observations with capture time, post age, maturity horizon, provenance, integrity flags, metric version, and payload hash.
- `outcome_collection_jobs`: durable maturity-window jobs; protected admin collection endpoint exists, but no external scheduler is active yet.
- `usage_events`: latency, bytes, tokens, success, and optional verified cost. Cost stays NULL until real pricing is configured.
- `seed_videos`, `calibration_notes`, correction/calibration fields: legacy research infrastructure; never feed them into live craft reviews.

Key services and routes:

- `routers/analyze.py`: upload/review, owner serialization, manual outcomes, provider links, and `GET /api/analyses/{id}/outcomes`.
- `services/gemini.py`: uploads media, applies injection-resistant system/data separation, returns six dimensions plus qualitative critique and a next experiment. It removes legacy aggregate/prediction fields from new output.
- `services/outcomes.py`: computes post age, assigns fixed maturity windows, and stores immutable snapshots.
- `services/tiktok_fetch.py` / `instagram_fetch.py`: untrusted provider adapters. Missing required counts fail closed; optional fields remain NULL.
- `services/telemetry.py`: provider/model operational telemetry. Do not claim cost or margin until pricing and payload measurements are verified.
- `services/economics.py`: admin operations report with measured reliability, unit coverage, row counts, and explicit unknown cost/margin fields.
- `services/niche_classifier.py`: canonicalizes niche context; failures use `UNCATEGORIZED` rather than guessing.
- `services/craft_insights.py`: descriptive craft-vs-verified-outcome aggregation for one creator (`GET /api/me/craft-insights`). Correlational only, gated by justified sample sizes; never causal, never a pixel-based forecast.
- `auth.py`: JWT helpers and the single canonical `is_minor()` implementation.
- `routers/settings.py`: account deletion removes analyses, artifacts, snapshots, and usage events in FK-safe order.

TikWM and HikerAPI are operational dependencies with rate-limit, schema-drift, availability, legal/ToS, and cost risks. Provider fields without local real-payload verification must be documented as “documented but not runtime-verified.” Store provenance and fail transparently.

New tables are created by `create_all`. Existing-column additions require model updates plus both SQLite and Postgres additive shims in `main.py`.

### Frontend

- `app/page.tsx`: positions Surge as craft review plus learn-from-each-post experimentation.
- `app/results/[id]/page.tsx`: AI craft dimensions, explicit evidence notice, recommended experiment, and a separate 24h/7d/30d outcome timeline.
- `app/results/[id]/improve/page.tsx`: editing hypotheses and next experiment; no projected performance.
- `app/projects/page.tsx`: named project history, with unlinked posts sorted first and then newest-first; mixed-age latest counts are not comparisons.
- `app/sample/page.tsx`: static example showing critique and observed results as separate evidence.
- `app/insights/page.tsx`: "Craft vs. Your Results" — the creator's own craft scores against their verified outcomes, with an honest empirical like-rate range and a correlation-not-causation notice.
- `components/VerdictBanner.tsx`: qualitative craft verdict only.
- `components/FeedbackModal.tsx`: manual unverified observations; provider fetches are preferred where available.
- `lib/api.ts`: typed review and outcome contracts.
- `components/Skeleton.tsx` and shared motion rules in `app/globals.css`: reusable dark-theme loading shapes, delayed shimmer, busy indicators, focus states, and reduced-motion behavior. Prefer page-shaped skeletons for unavailable content and localized busy feedback for background refreshes.
- `components/ReactiveVideoDropzone.tsx`: shared guest/authenticated upload target with pointer spotlight, drag state, validated-file state, keyboard operation, and matching transfer progress styling from `app/globals.css`.

Next.js 15 App Router requires `"use client"` for hooks such as `useParams`, `useSearchParams`, and auth state. The theme is dark-only. PWA assets are under `frontend/public`.

## Security, privacy, and reliability

- Rate checks run before Gemini calls. Re-raise Gemini 429/403 so callers receive 503 rather than a fabricated report.
- Never log secrets or raw uploaded media. Provider raw payloads are not retained; a hash may be stored for traceability.
- Account deletion must delete user-owned review and measurement data, not merely anonymize it.
- Consent to measurement research never turns observational data into causal evidence.
- Exact hashes prevent duplicate uploads; near-duplicate detection is not implemented yet and must be added before any evaluation dataset is trusted.
- There is no scheduler for automatic 24h/7d/30d refreshes yet; users manually capture near those windows.
- Cost, refresh cost, storage growth, latency distribution, and gross margin remain unverified until real production telemetry is collected. Do not invent estimates from absent payloads.

## Environment variables

- `GEMINI_API_KEY`, `JWT_SECRET`, `ADMIN_PASSWORD`, `ALLOWED_ORIGINS`, `DATABASE_URL`
- `NEXT_PUBLIC_API_URL`, `SMTP_HOST/PORT/USER/PASS`, `EMAIL_FROM`, `FRONTEND_URL`
- `HIKERAPI_KEY`; R2 variables if upload persistence is enabled

## Legal documents

The Terms of Service lives at `frontend/app/terms/page.tsx`. If the website URL ever changes from `withsurge.com`, update every occurrence of `withsurge.com` in that file to match the new URL.

## Deploy discipline

Railway is on a limited free plan. Backend deploys must be batched.

1. Do not deploy or push without explicit instruction.
2. Run backend tests/compile and frontend typecheck/build locally before a push.
3. Combine schema and backend code in one verified push.
4. Do not spend a backend deploy on a typo or log-only change.
5. Before any backend push, ask: “Can I combine this with anything else that's pending?”
