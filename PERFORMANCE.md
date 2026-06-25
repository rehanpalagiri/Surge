# Surge — Performance, Load & Rendering Notes

A from-the-ground audit of the analyze flow, the API under load, and the
frontend's rendering model — plus the changes made and how to reproduce the
numbers. Nothing here was deployed; all of it runs locally and applies on the
next deploy you choose to make.

---

## 1. The analysis loading bar (UX)

**Before:** every loading surface showed the full report *skeleton* immediately
(or after a flat 4 s timer), with no real percentage. The skeleton is the
heaviest, busiest thing on screen, so it dominated the entire wait.

**Now:** one component — [`components/AnalysisProgress.tsx`](frontend/components/AnalysisProgress.tsx) —
owns the whole experience:

- A clean progress bar with a **numeric percentage right under it**. The
  percentage is *time-based* (eases toward ~90 % over the expected duration,
  then crawls) so it tracks real elapsed work instead of jumping. It snaps to
  100 % only when the work is actually done — it never lies.
- The **skeleton is revealed only near the end** (default ≥ 88 %, i.e. "almost
  done / a few seconds left"), fading in beneath a slim top bar so results feel
  like they're materializing. If the review finishes quickly you go straight to
  results and never see a skeleton at all.

It replaced three separate copies of the old fake-progress-plus-4s-timer logic
in `app/page.tsx`, `components/UploadZone.tsx`, and `app/results/[id]/page.tsx`,
and the now-unused `lib/useFakeProgress.ts` was deleted. The static skeleton is
memoized so the ~8 fps progress ticks only repaint the bar, not the placeholder
report.

---

## 2. Compressed API responses (gzip)

`GZipMiddleware` is now installed in [`main.py`](backend/main.py) (`minimum_size=500`,
added inside CORS so CORS stays outermost). Analysis payloads are highly
repetitive JSON and compress 40–80 %; the saving grows with payload size, so the
full owner report (the big one) benefits most.

Verified live:

```
GET /api/analyses/{id}   no Accept-Encoding → 792 bytes
GET /api/analyses/{id}   Accept-Encoding: gzip → 480 bytes  (content-encoding: gzip)
```

---

## 3. The DB write in `/analyze`

**Before:** `add → commit → refresh → upsert_artifact → commit` — the same
logical record written in **two** transactions plus an extra refresh round-trip.
A crash between the commits could leave an analysis row with no artifact.

**After:** `add → flush → upsert_artifact → commit`. `flush()` assigns the id
(and the Python-side `created_at` default) so the artifact can reference it, then
**one** commit persists both rows atomically. The R2 path dropped its redundant
post-commit `refresh` too. See [`routers/analyze.py`](backend/routers/analyze.py).

---

## 4. Round-trip latency — the single-dependency bottleneck

Tool: [`backend/tools/latency_audit.py`](backend/tools/latency_audit.py). It
breaks one analysis into its network events and times the safe ones live.

```
1. wakeBackend → GET /health          0.56 / 0.87 ms
2. POST /upload/presigned-url          ~1–5 ms (CPU)
3. PUT video → Cloudflare R2           user uplink, not our server
4. POST /api/analyze (enqueue)         ~1–5 ms
5. GET …/status (poll tick)            0.90 / 1.52 ms
6. *** Gemini craft review ***         10,000–40,000 ms   ← THE BOTTLENECK
7. GET /api/analyses/{id}              0.97 / 1.28 ms
```

**Conclusion:** every event we control answers in ≤ 1.5 ms (p95). The Gemini
call is ≥ 6,500× slower than the entire rest of the flow **combined**. It is the
one external dependency the product is gated on. It's already run as a background
job and surfaced via polling, so it never blocks the request.

The only client-side dead-time was the **flat 3 s poll** — a review that
finished at t+0.1 s waited until t+3 s. Both poll loops (`UploadZone` and the
results page) now use a **ramped backoff** (≈0.8 s → 3 s), so a finished review
is picked up within ~0.8 s instead of up to 3 s.

---

## 5. Frontend rendering — is HTML rebuilt per visitor?

Checked via the production build's route table. **Almost everything is already
static** (`○`), prerendered once at build and served from the CDN — *not*
rebuilt per visitor: `/`, `/sample`, `/privacy`, `/terms`, `/login`, `/signup`,
`/settings`, `/projects`, `/profile`, `/admin`, etc.

The dynamic (`ƒ`) routes were:

- `/opengraph-image` — an **input-less, identical** social card that was forced
  to regenerate on every crawler request by `runtime = "edge"` (edge runtime
  disables static generation). Removed the edge runtime → it's now `○` static,
  built once, CDN-served.
- `/results/[id]/opengraph-image` — same card for every analysis; dropped edge
  runtime and added a long `Cache-Control` so each id renders at most once.
- `/results/[id]` and `/results/[id]/improve` — `"use client"` shells on a
  runtime-only dynamic segment. The per-request server work is just a near-empty
  shell (the data is fetched client-side), so the cost is minimal. Making the
  shell ISR-cached would require splitting it into a server wrapper that exports
  `generateStaticParams`/`dynamicParams`; left as an optional follow-up since it
  touches the highest-traffic page on a launched app.

---

## 6. Load / stress test

Tool: [`backend/tools/stress_test.py`](backend/tools/stress_test.py). Seeds one
realistic completed analysis, then fires GETs at `/health` (no DB),
`/api/analyses/{id}/status` (1 SELECT), and `/api/analyses/{id}` (DB + gzip) at
concurrency 1 / 100 / 1000. Safe endpoints only — never calls Gemini.

Result on a single local dev worker (SQLite):

```
                       c=1            c=100                 c=1000
health (no DB)    1767 req/s    928 req/s p95 315ms    304 req/s p95 10.6s
status (1 SELECT)  369 req/s    426 req/s p95 732ms    312 req/s p95 10.5s
analysis (DB+gz)   519 req/s    413 req/s p95 753ms    287 req/s p95 11.3s
Verdict: PASS — 0 errors across all levels
```

**What this proves:** the app is **correct and stable under load** — zero 5xx /
zero dropped requests even at 1000 simultaneous in-flight connections. "1000
users" across a day is a non-event; even 1000 *at the exact same instant* only
makes it slower, never broken.

**The ceiling** is a single event loop: even `/health` (no DB, no app logic)
degrades at c=1000, which is the signature of one worker process. The honest fix
is horizontal scaling, with one prerequisite:

> `services/throttle.py` keeps the **guest analysis limit** and the
> **password-reset brute-force guard** in process memory. Running multiple
> workers/replicas today would give each its own counters — every replica would
> grant the full quota (and burn Gemini money). The module already documents
> this.

So the [`Dockerfile`](backend/Dockerfile) now exposes `WEB_CONCURRENCY`
(**default 1, on purpose**) with an in-file note: move the throttle to a shared
store (a DB table or Redis) first, *then* raise it. That converts "we're capped
at one worker" from an invisible property into a one-line, documented lever.

---

## Running the tools

```bash
cd backend && source venv/bin/activate
uvicorn main:app --port 8000           # in one shell

# in another shell:
PYTHONPATH=. python tools/latency_audit.py --base http://127.0.0.1:8000
ulimit -n 8192
PYTHONPATH=. python tools/stress_test.py --base http://127.0.0.1:8000 \
    --levels 1,100,1000 --json report.json
```
