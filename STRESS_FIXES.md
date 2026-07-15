# Stress-Test Fixes — Master Work Order

Each section below is a **self-contained prompt**. Copy one into a fresh Claude Code session
(or hand it to a subagent) and it has everything needed: exact file(s), the current code to
locate, the change, the reason, the project constraints, and how to verify.

They are ordered by **leverage ÷ risk**. **1–3 are low-risk wins that help TODAY on the current
single-worker deploy.** 4 is a higher-risk refactor with a payoff. 5 is the largest effort and is
only needed when you actually scale beyond one worker.

## Where these came from (context for the implementer)

A production stress test (Railway backend `WEB_CONCURRENCY=1`, one uvicorn worker → one event loop)
found and measured:

- **bcrypt blocks the single event loop.** 4 concurrent signups serialized to ~2.4s each (parallel
  would be ~0.5s) and an unrelated `/health` spiked from ~150ms to **980ms** during the burst. On
  one event loop, every password hash freezes the whole API.
- **DB routes hard-cap at ~24 req/s** while latency climbs to multiple seconds under load; non-DB
  routes do ~233 req/s. The DB layer (default 15-connection pool + Neon round-trip) is the ceiling.
- **`/api/auth/signup` has no rate limit**, so the event-loop stall above is trivially triggerable
  by anyone, unauthenticated.

Prompts 1–5 below fix the mechanisms behind those measurements.

## Shared constraints that apply to EVERY prompt (from `CLAUDE.md` / `AGENTS.md`)

- Do **not** deploy, push, or trigger Railway. Do not commit unless asked.
- Backend gate before finishing:
  `cd backend && source venv/bin/activate && GEMINI_API_KEY=dummy PYTHONPATH=. python -m unittest discover -s tests`
  and `python -m compileall -q .`. Tests need a (dummy) `GEMINI_API_KEY` to import the Gemini client;
  do **not** set `ADMIN_PASSWORD` (the collect-due test relies on the `viraliq-admin` dev default).
- Frontend gate (only if you touched `frontend/`): `cd frontend && npx tsc --noEmit && npm run build`.
- Every new limit / pool number needs a **stated justification** — no invented round numbers.
- Existing-table column additions require a model update PLUS additive shims in `main.py`
  (`_ensure_columns` for SQLite AND `_ensure_columns_pg` for Postgres). `create_all` covers new tables.
- **Batch these into ONE backend deploy** — per deploy discipline, don't spend a Railway deploy on
  one of these alone. (You are NOT deploying now; just don't split them into many pushes later.)
- Preserve unrelated local changes.
- Locate edits by the quoted snippet, not a line number (numbers drift).

---

## PROMPT 1 — Move bcrypt off the event loop (HIGH leverage, LOW risk — do first)

**Files:** `backend/auth.py` (add async wrappers), `backend/routers/auth.py` and
`backend/routers/settings.py` (await at the call sites).

**Problem.** `hash_password` / `verify_password` run `bcrypt` (cost factor 12, ~200–400ms of pure
CPU) **synchronously inside `async def` handlers**. Production runs one worker = one event loop, so a
single hash freezes every other in-flight request. Measured: 4 concurrent signups serialized to
~2.4s and stalled an unrelated `/health` to 980ms.

**Locate this exact code in `backend/auth.py`:**
```python
def hash_password(password: str) -> str:
    # bcrypt only considers the first 72 bytes; truncate to avoid a ValueError.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:72], password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False
```

**Change.** Keep the sync functions (they are the thread target and are used by the module-level
`_DUMMY_PW_HASH` constant, which runs once at import — leave that one sync). Add async wrappers right
below them (add `import asyncio` at the top of `auth.py` if not present):
```python
async def hash_password_async(password: str) -> str:
    # bcrypt is CPU-bound and releases the GIL during hashing, so a worker thread
    # runs it truly in parallel and keeps the single event loop free for other
    # requests (prod is WEB_CONCURRENCY=1 — one hash inline stalls the whole API).
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(verify_password, password, password_hash)
```

Then update **every async-handler call site** to await the async version and import it:

- `backend/routers/auth.py` — import `hash_password_async, verify_password_async`; then:
  - signup: `password_hash=hash_password(payload.password)` → `password_hash=await hash_password_async(payload.password)`
  - login: `verify_password(payload.password, user.password_hash if user else _DUMMY_PW_HASH)` → `await verify_password_async(...)`
  - google_auth: `password_hash=hash_password(secrets.token_urlsafe(32))` → `password_hash=await hash_password_async(...)`
  - reset_password: `user.password_hash = hash_password(payload.new_password)` → `await hash_password_async(...)`
- `backend/routers/settings.py` — import `hash_password_async, verify_password_async`; update the two
  `verify_password(body.current_password, ...)` checks, the `verify_password(body.password, ...)` in
  delete_account, and the `user.password_hash = hash_password(body.new_password)` to their awaited
  async forms.

**Leave unchanged:** the module-level `_DUMMY_PW_HASH = hash_password("...")` in `routers/auth.py`
(import-time constant, not in a request path). The constant-work login path must still run bcrypt on
`_DUMMY_PW_HASH` for nonexistent users — keep that timing-equalizer behavior via `verify_password_async`.

**Acceptance criteria.**
- Grep confirms no `async def` handler calls the bare sync `hash_password`/`verify_password` anymore
  (only the module constant and the async wrappers do).
- `verify_password_async(pw, await hash_password_async(pw))` round-trips `True`; a wrong password → `False`.
- Login still runs a hash for a nonexistent user (no early return) so timing can't enumerate accounts.
- Backend tests + `compileall` pass.

---

## PROMPT 2 — Rate-limit signup (HIGH value, LOW risk)

**File:** `backend/routers/auth.py` (the `signup` handler).

**Problem.** Every other unauthenticated auth-mutation endpoint (`login`, `forgot-password`,
`resend-verification`, `verify-*`, `reset-*`) is guarded by `check_rate`, but `signup` is not. Each
signup is expensive — a bcrypt hash + a Brevo verification email + two DB commits — so an
unauthenticated flood is both an event-loop stall (see PROMPT 1) and a real email/DB cost vector.

**Locate the signature:**
```python
@router.post("/signup", response_model=TokenOut)
async def signup(payload: SignupIn, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
```

**Change.** Add `request: Request` to the signature and a throttle at the very top of the body.
`Request`, `check_rate`, and the `_client_ip` helper are already imported/defined in this file
(login uses them):
```python
@router.post("/signup", response_model=TokenOut)
async def signup(payload: SignupIn, request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    # Brute-force / spam guard: signup is unauthenticated and expensive (bcrypt +
    # a verification email + two DB commits). Keyed on the real client IP.
    if not check_rate(f"signup-ip:{_client_ip(request)}", max_hits=5, window_seconds=900):
        raise HTTPException(
            status_code=429,
            detail="Too many sign-up attempts. Please wait a few minutes and try again.",
        )
    email = payload.email.strip().lower()
```

**Justification for 5 / 900s (state it, don't invent a round number).** Signing up is a rare,
one-time action per person; the only legitimate reason one IP creates several accounts in minutes is
shared NAT (offices, campuses, mobile carriers). 5 per 15 minutes absorbs that and honest retries
while capping automated creation to ~20/hour/IP — far below any spam threshold — and it matches the
existing `forgot-password` / `resend-verification` guards (also 5 / 900s) for a consistent policy on
unauthenticated auth mutations.

**Acceptance criteria.**
- A test that POSTs `/api/auth/signup` 6 times from one client IP gets `429` on the 6th (first 5 pass
  or fail on their own merits, not the limiter).
- Distinct IPs get independent buckets (uses `_client_ip`, i.e. the rightmost trusted `X-Forwarded-For`
  hop — never the spoofable leftmost entry).
- Backend tests + `compileall` pass.

---

## PROMPT 3 — Size the DB connection pool explicitly (LOW risk, config only)

**File:** `backend/database.py` (the **Postgres** branch of `_build_engine` only).

**Problem.** The Postgres engine sets no `pool_size` / `max_overflow` / `pool_timeout`, so it inherits
SQLAlchemy's async defaults: **5 + 10 = 15** connections and a **30-second** checkout timeout. That 15
is the ceiling every DB route shares (measured: DB throughput plateaus ~24 req/s), and the 30s timeout
means an overloaded request hangs for 30s before it errors instead of failing fast.

**Locate this exact code:**
```python
    return create_async_engine(
        clean,
        echo=False,
        connect_args=connect_args,
        pool_pre_ping=True,   # re-validate connections before use; drops dead ones
        pool_recycle=300,     # recycle after 5 min — before Neon's idle timeout closes them
    )
```

**Change.** Add explicit pool arguments (Postgres branch ONLY — do **not** touch the SQLite branch;
`aiosqlite` doesn't use this pool the same way):
```python
    return create_async_engine(
        clean,
        echo=False,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_recycle=300,
        # Explicit sizing (was the implicit 5+10=15 / 30s default). Total connections
        # this process can open = pool_size + max_overflow. With WEB_CONCURRENCY=1 that
        # is 20; if you ever raise WEB_CONCURRENCY or add replicas, total becomes
        # workers * (pool_size + max_overflow) and MUST stay under Neon's max_connections
        # for this plan — verify that number before scaling. Shorter pool_timeout so an
        # overloaded backend rejects fast instead of hanging 30s on a checkout.
        pool_size=10,
        max_overflow=10,
        pool_timeout=10,
    )
```

**Before finalizing:** confirm Neon's `max_connections` for the current plan (Neon dashboard, or
`SHOW max_connections;`) and ensure `workers * (pool_size + max_overflow)` stays comfortably under it.
If the plan's limit is tight, lower these numbers and say so in the comment. Do not ship a bare number.

**Acceptance criteria.**
- The SQLite branch is unchanged; only the Postgres `create_async_engine` gains the three args.
- App boots and `compileall` passes. (Backend tests run on SQLite, so they won't exercise this — that's
  expected; the change is a production-Postgres behavior. Confirm the engine constructs without error.)

---

## PROMPT 4 — Stop holding a DB connection across the Gemini call (MEDIUM-HIGH, higher risk)

**Files:** `backend/routers/analyze.py` (the direct file/URL path in `analyze`, plus a background
helper). Frontend: verify only — likely no change needed.

**Problem.** The **direct** file-upload / TikTok-URL path pre-creates the row with `await db.flush()`
(which opens a transaction and checks out a pool connection) and then `await analyze_video(...)` — the
30–90s Gemini upload + poll + two passes — before it commits. One request holds a pool connection AND
an open Postgres transaction for the whole external call; a handful of concurrent direct analyses
starve the 15/20-connection pool (see PROMPT 3) and every DB route queues behind them. The **R2 path
already does it right**: it creates a `status="pending"` row, commits immediately, and backgrounds the
work via `_run_r2_analysis`, returning `{"id", "status": "pending"}`.

**Locate the synchronous tail** in `analyze` — from:
```python
    content_sha256 = sha256_file(file_path)

    # Pre-create the analysis row to get an ID for usage-event telemetry.
    ...
    db.add(analysis)
    await db.flush()

    try:
        result = await analyze_video(
            file_path,
            canonical_niche,
            ...
```
through the final `await db.commit()` and `return _to_out(analysis, include_claim_token=True)`.

**Change.** Make this path mirror the R2 path:
1. Create the `UserAnalysis` row with `status="pending"` (keep the `guest_claim_token` for guests) and
   `await db.commit()` — so the id is durable and the connection/transaction is released immediately.
2. `background_tasks.add_task(_run_local_analysis, analysis.id, file_path, uploads_dir, user.id if user else None, raw_niche, canonical_niche, caption, bio, platform, niche_needs_confirmation, secondary_niche, resolved_parent_id)`.
3. Return `{"id": analysis.id, "status": "pending"}` plus `claim_token` when `analysis.guest_claim_token`
   is set — exactly like the R2 branch's return shape.

Add a **`_run_local_analysis`** background helper modeled on `_run_r2_analysis`, but the file is
already on local disk so it SKIPS the R2 `object_size`/`download` step. Reuse the shared finalize logic:
set `status="processing"`, compute `sha256_file`, call `analyze_video`, then write the result exactly
as `_run_r2_analysis` does (`niche`/`canonical_niche`/`scores_json`, and `status="error"` + `verdict="Error"`
when `result.get("error")`, else `status="complete"`), `upsert_artifact`, commit, and delete the temp
file in a `finally`. **Recommended:** factor the shared tail of `_run_r2_analysis` (everything from
`result = await analyze_video(...)` onward, plus the temp-file cleanup) into one
`_finalize_analysis(analysis_id, file_path, ...)` helper and call it from both `_run_r2_analysis` and
`_run_local_analysis`, so there is one code path for "write the Gemini result and clean up."

**Keep the ordering:** rate-limit + validation still run BEFORE the row is created (no Gemini quota
burned on rejected requests) — it already does; preserve that.

**Behavior change to call out (intended).** Today the direct path re-raises a Gemini 429/403 as an HTTP
`503` to the caller. After backgrounding, the caller already has `{"status": "pending"}`, so a 429/403
in the background becomes a `status="error"` the results page surfaces — identical to the R2 path. This
is the correct, consistent behavior; note it in the PR description.

**Frontend (verify, don't assume).** `lib/api.ts::analyzeVideo` already only reads `{id, claim_token}`
from the response, and `app/results/[id]/page.tsx` already polls `getAnalysisStatus` while an analysis
is `processing`/`pending`. So the direct-upload flow (`app/page.tsx` → navigate to `/results/{id}`)
should transparently pick up the pending→complete polling. **Verify** end-to-end that a file upload and
a TikTok-URL analysis both land on the results page and resolve after polling, with a correct loading
state — and confirm `npx tsc --noEmit && npm run build` pass. Make a frontend change only if that flow
regresses.

**Acceptance criteria.**
- No code path holds a DB connection/transaction across `analyze_video` (grep: no `analyze_video` call
  sits between a `flush`/`add` and a later `commit` on the request's `db` session).
- Direct file upload AND TikTok-URL analysis both return `{"id", "status": "pending"}` and complete via
  the background task; the results page shows the finished report.
- A background Gemini 429/403 yields `status="error"` (no credit charged), matching the R2 path.
- Backend tests + `compileall` pass; frontend `tsc`/`build` pass. Add/adjust a test that the direct path
  returns `pending` and the background task finalizes the row.

---

## PROMPT 5 — Externalize the in-memory throttle + pending-upload state (LARGEST effort, do last)

**Files:** `backend/services/throttle.py`, `backend/routers/analyze.py` (`_pending_uploads`),
`backend/models.py` (+ shims in `backend/main.py`). Also `backend/Dockerfile` (comment).

**Problem.** `check_rate`'s `_hits` deque and `analyze.py`'s `_pending_uploads` dict live in **process
memory**. That is why `Dockerfile` pins `WEB_CONCURRENCY=1` — a second worker or replica would keep its
own counters (each granting the full quota) and wouldn't see the other's upload keys. This in-memory
state is the hard blocker to horizontal scaling, which is the real throughput lever once the single
event loop is saturated (prompts 1–4 make one worker healthier but can't add a second one).

**Approach (DB-backed, consistent with the stack — no Redis today).**
- Add a `rate_limit_hits` table (`key VARCHAR index`, `hit_at TIMESTAMP index`). Reimplement
  `check_rate` as: delete rows for `key` older than `now - window`, count what remains, and insert a new
  row iff `count < max_hits` — the same sliding-window semantics as the current deque, just durable and
  shared. Keep the periodic stale-row sweep (a bounded `DELETE ... WHERE hit_at < now - MAX_WINDOW`).
- Replace `_pending_uploads` with a `pending_uploads` table (`r2_key` PK, `user_id` nullable,
  `issuer_ip`, `issued_at`); `_prune_pending` becomes a `DELETE` of stale rows, and the `pop` becomes a
  `SELECT ... FOR UPDATE` + `DELETE`.
- These calls now touch the DB, so `check_rate` / `client_ip` usage becomes async — ripple `await` to
  all call sites in `routers/auth.py` and `routers/analyze.py`.
- New tables come from `create_all`; add the additive shims to BOTH `_ensure_columns` (SQLite) and
  `_ensure_columns_pg` (Postgres) in `main.py` for any columns on existing tables (new tables need no
  shim, but keep the pattern consistent).

**Honest tradeoff to state in the PR.** DB-backed throttling adds queries to the layer that is already
the measured bottleneck (the 15/20-conn pool, PROMPT 3). It is acceptable here because the throttled
endpoints (auth, password reset, guest upload) are **low-volume** — but if you plan serious horizontal
scaling, **Redis** (`INCR` + `EXPIRE`, or a sorted-set sliding window) is the better fit: it keeps this
load off the primary DB entirely. Recommend Redis if the infra allows; otherwise the DB table is fine
for the current throttle volume. Do NOT silently move high-QPS state to the primary DB without noting
this.

**Also:** once state is shared, update the `WEB_CONCURRENCY=1` guardrail comment in `backend/Dockerfile`
to say the in-memory constraint is lifted — but remember that raising workers multiplies the DB pool
(PROMPT 3): keep `workers * (pool_size + max_overflow)` under Neon's `max_connections`.

**Acceptance criteria.**
- Throttle counters and pending-upload keys are visible across processes (a second worker enforces the
  same limits and can consume an upload key issued by the first).
- Existing throttle behavior is unchanged from a caller's perspective (same limits, same 429s); existing
  throttle/upload tests pass, plus a new test proving persistence across two sessions/"processes".
- New tables created by `create_all`; any existing-table columns covered by BOTH engine shims.
- `Dockerfile` comment updated. Backend tests + `compileall` pass.
- **This is the biggest change of the five and the lowest urgency** — prompts 1–4 improve the current
  single-worker deploy immediately; ship 5 only when you actually need to run more than one worker.

---

## Suggested sequencing

1. **PROMPT 1 + 2 + 3** together — small, low-risk, and they directly address the measured event-loop
   stall, the unthrottled abuse door, and the fail-slow pool. One verified backend batch.
2. **PROMPT 4** next, on its own, with full end-to-end verification of the upload → results-polling flow
   (it changes the direct-analyze response contract, even though the frontend already tolerates it).
3. **PROMPT 5** only when horizontal scaling is on the table; prefer Redis if available.

None of this is a substitute for keeping `WEB_CONCURRENCY=1` until PROMPT 5 lands — with shared state
still in memory, more than one worker would break the rate limits.
