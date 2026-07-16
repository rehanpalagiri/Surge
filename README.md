# CraftLint

Creators post a video, get a view count, and learn nothing. Was it the hook? The pacing? The caption? There's no way to isolate what actually moved the needle — so nobody actually improves, they just keep guessing.

CraftLint turns every post into a controlled experiment. It reviews the editing choices that drive attention — hook, pacing, text, curiosity, audio/visual sync, ending strength — proposes **one** focused change to test next, then tracks the real public metrics of the post at fixed, comparable time windows (24h, 7d, 30d) so a creator can tell, with actual evidence, whether the change worked.

It's a craft linter plus a split-testing tracker for short-form video — not a virality predictor. We think predicting views is a losing game (platforms are too noisy, too gameable); helping creators run a real feedback loop on their own craft is not.

## Product flow

1. Upload a TikTok or Reel and choose its niche context.
2. Receive six independent craft assessments, evidence-based notes, rewrites, and one recommended experiment.
3. Link the published post or enter public metrics manually.
4. Capture observations near 24 hours, 7 days, and 30 days.
5. Compare only like-aged observations and use the result to choose the next experiment.

Likes divided by views is displayed only as **observed like rate**. It is not content quality. Instagram remains likes-only unless its reach denominator is runtime-verified.

## Stack

- Next.js 15 + TypeScript + Tailwind CSS
- FastAPI + async SQLAlchemy
- SQLite locally, Neon Postgres in production
- Google Gemini for media review
- TikWM and HikerAPI for optional public-metric capture
- Vercel frontend, Railway backend

## Local development

```bash
# Backend
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.

## Verification

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. python -m unittest discover -s tests
python -m compileall -q .

cd ../frontend
npx tsc --noEmit
npm run build
```

## Evidence and data rules

- Outcome snapshots are immutable and retain capture time, post age, source, integrity flags, metric version, and provider-payload hash.
- Fixed windows are 24h ±6h, 7d ±24h, and 30d ±72h. Off-window captures are stored but not assigned to a maturity window.
- Manual metrics are marked unverified.
- Video, captions, usernames, comments, metadata, and provider payloads are treated as untrusted input.
- Exact duplicate hashes are captured. Near-duplicate detection is not implemented and must exist before any model evaluation dataset is trusted.
- Any future evaluation must group all posts from one creator into one split and use chronological holdouts.
- Public engagement can be distorted by purchases, bots, pods, giveaways, rage bait, spam, creator comments, and controversy.

## Provider and economics status

TikWM and HikerAPI carry availability, rate-limit, schema-drift, pricing, legal/ToS, and platform-policy risk. Fields inferred from documentation but not seen in a local real payload are **documented but not runtime-verified**.

`usage_events` records latency, payload bytes, tokens when available, success, and optional verified cost. The protected `/api/admin/operations/report` endpoint summarizes measured coverage and keeps unknown cost and margin fields explicitly null. Until production telemetry and contracted provider/model pricing are available, per-analysis cost, refresh cost, latency distribution, storage growth, and gross margin are unverified. CraftLint does not substitute invented round numbers for missing measurements.

## Deployment

The backend self-creates new tables at startup. Do not deploy or push without explicit instruction. Batch backend changes, test locally, and ship schema plus code together.
