# ViralIQ

AI-powered TikTok video performance predictor. Upload a video, get an instant breakdown of hook strength, pacing, audio, captions, trend alignment — plus a prioritised improvement plan with rewritten hooks and captions.

**Stack:** FastAPI · Next.js 15 · Google Gemini 2.5 Flash · Neon Postgres  
**Auth:** JWT — freemium gate enforced server-side (anonymous users see verdict only; sign up free to unlock full analysis)

---

## Local development

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # fill in GEMINI_API_KEY and JWT_SECRET
uvicorn main:app --reload --port 8000
```
Local dev uses **SQLite by default** — no DB setup needed. Leave `DATABASE_URL` unset in `.env`.  
API docs: http://localhost:8000/docs

### Frontend
```bash
cd frontend
npm install
# create frontend/.env.local with one line:
#   NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```
Open http://localhost:3000 · Admin: http://localhost:3000/admin

---

## Production deployment

### Services
| Service | Purpose |
|---|---|
| [Neon](https://neon.tech) | Postgres database (free tier, 0.5 GB) |
| [Render](https://render.com) | FastAPI backend — Docker container (free tier) |
| [Vercel](https://vercel.com) | Next.js frontend (free tier) |

### Step 1 — Neon (database)
1. Create a free project at neon.tech — region **AWS US East 1**
2. Go to **Connection Details** → select **Direct** (not Pooler)  
3. Copy the connection string:  
   `postgresql://user:pass@ep-xxx.us-east-1.aws.neon.tech/neondb?sslmode=require`

Tables are created automatically on first backend boot (`Base.metadata.create_all`).  
> **Use the Direct URL, not the Pooler URL**, on Render — it's a long-lived process and direct connections are faster. If you must use the pooler, asyncpg's statement cache is automatically disabled to avoid pgbouncer errors.

### Step 2 — GitHub
```bash
cd viraliq      # repo root
git init
git add .
git commit -m "Initial commit"
gh repo create viraliq --private --source=. --push
# or manually: git remote add origin https://github.com/YOU/viraliq.git && git push -u origin main
```

### Step 3 — Render (backend)
1. Render Dashboard → **New → Blueprint**
2. Connect your GitHub repo — Render finds `backend/render.yaml` automatically
3. Set these **secret** environment variables in the Render dashboard (never committed):

| Variable | Value |
|---|---|
| `DATABASE_URL` | Your Neon direct connection string |
| `GEMINI_API_KEY` | Your Google AI Studio API key |
| `ADMIN_PASSWORD` | A strong password for the `/admin` panel |
| `JWT_SECRET` | Run: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ALLOWED_ORIGINS` | Set **after** Vercel deploy (e.g. `https://viraliq.vercel.app`) |

4. Deploy — Render builds the Dockerfile; first boot creates all Neon tables automatically
5. Verify: `https://your-app.onrender.com/health` → `{"status":"ok"}`

### Step 4 — Vercel (frontend)
1. Vercel Dashboard → **New Project** → Import from GitHub
2. Set root directory to **`frontend`**
3. Add one environment variable:
   - `NEXT_PUBLIC_API_URL` = `https://your-app.onrender.com` (your Render URL, no trailing slash)
4. Deploy and note your Vercel URL (e.g. `https://viraliq.vercel.app`)

### Step 5 — Wire CORS
Back in Render dashboard → **Environment** → update `ALLOWED_ORIGINS` to your Vercel URL → **Save Changes** (triggers auto-redeploy).

### Step 6 — End-to-end test
1. Open your Vercel URL
2. Upload a video (logged out) → you should see verdict + locked overlay + upsell modal
3. Sign up → result unlocks, appears in My Projects
4. Open My Projects — analysis is persisted in Neon ✓

---

## Environment variables

### Backend (`backend/.env` locally · Render secrets in production)
| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Google AI Studio API key |
| `JWT_SECRET` | ✅ | Long random string for signing auth tokens |
| `ADMIN_PASSWORD` | ✅ | Password for the `/admin` panel |
| `ALLOWED_ORIGINS` | ✅ | Comma-separated frontend origins for CORS |
| `DATABASE_URL` | prod only | Neon connection string (omit locally → SQLite) |

### Frontend (`frontend/.env.local` locally · Vercel env vars in production)
| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | prod only | Backend URL (omit locally → `http://localhost:8000`) |

> ⚠️ **Never commit secrets.** `backend/.env` and `frontend/.env.local` are gitignored.

---

## Architecture notes

- **Freemium gate — server-side.** Anonymous `GET /api/analyses/{id}` returns only `{verdict, predicted_views, locked:true}` — full scores/plan never leave the backend until the user is authenticated.
- **Neon TLS.** asyncpg requires SSL via `connect_args`, not the URL. We use `certifi`'s CA bundle — works on macOS (Python from python.org doesn't trust the system keychain) and Linux/Render equally.
- **SQLite ↔ Postgres.** Set `DATABASE_URL` to switch. The idempotent column-migration shim (`_ensure_columns`) only runs on SQLite where `ALTER TABLE ADD COLUMN IF NOT EXISTS` doesn't exist; Postgres gets full schema from `create_all`.
- **TikTok auto-fetch (yt-dlp).** Works locally for seeding your database. Blocked on Render (datacenter IPs) — that's expected; seed locally and redeploy.

---

## Project structure

```
viraliq/
├── backend/
│   ├── main.py              # FastAPI app, CORS, lifespan startup
│   ├── database.py          # async SQLAlchemy engine (SQLite + Postgres)
│   ├── models.py            # User, SeedVideo, UserAnalysis, FetchStatus
│   ├── auth.py              # JWT + bcrypt helpers, require_user / optional_user
│   ├── routers/
│   │   ├── auth.py          # /api/auth/* (signup, login, /me)
│   │   ├── analyze.py       # /api/analyze, /api/analyses/*, /api/me/analyses
│   │   └── admin.py         # /api/admin/* (seed CRUD, yt-dlp fetch, fetch-status)
│   ├── services/
│   │   └── gemini.py        # Gemini 2.5 Flash async prompt + JSON parsing
│   ├── uploads/             # temp video storage (cleared after analysis)
│   ├── Dockerfile
│   ├── render.yaml          # Render Blueprint
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx                        # landing + upload
    │   ├── results/[id]/page.tsx           # results (locked or full)
    │   ├── results/[id]/improve/page.tsx   # full improvement plan (auth-gated)
    │   ├── login/page.tsx
    │   ├── signup/page.tsx
    │   ├── projects/page.tsx               # Past Projects
    │   └── admin/page.tsx
    ├── components/
    │   ├── Nav.tsx
    │   ├── UploadZone.tsx
    │   ├── ScoreBar.tsx
    │   ├── VerdictBanner.tsx
    │   ├── FeedbackModal.tsx
    │   └── UpsellModal.tsx
    ├── lib/
    │   ├── api.ts
    │   └── auth.ts
    └── package.json
```
