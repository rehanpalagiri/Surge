import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.datastructures import MutableHeaders

from database import engine
from models import Base
from routers.admin import router as admin_router
from routers.analyze import router as analyze_router
from routers.auth import router as auth_router
from routers.billing import router as billing_router
from routers.profile import router as profile_router
from routers.settings import router as settings_router


async def _ensure_columns(conn):
    """Lightweight idempotent migration: add columns to existing tables
    if they're missing (SQLite has no ALTER TABLE ADD COLUMN IF NOT EXISTS)."""
    # --- user_analyses ---
    result = await conn.exec_driver_sql("PRAGMA table_info(user_analyses)")
    existing = {row[1] for row in result.fetchall()}
    for col in ("caption", "bio"):
        if col not in existing:
            await conn.exec_driver_sql(
                f"ALTER TABLE user_analyses ADD COLUMN {col} TEXT"
            )
    if "project_name" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN project_name TEXT"
        )
    if "user_id" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN user_id INTEGER"
        )

    if "mode" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN mode TEXT DEFAULT 'quick'"
        )

    if "video_url" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN video_url TEXT"
        )
    if "counts_fetched_at" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN counts_fetched_at DATETIME"
        )
    if "guest_claim_token" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN guest_claim_token TEXT"
        )
    if "promoted_seed_id" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN promoted_seed_id INTEGER"
        )

    # --- seed_videos ---
    result = await conn.exec_driver_sql("PRAGMA table_info(seed_videos)")
    seed_cols = {row[1] for row in result.fetchall()}
    if "posted_at" not in seed_cols:
        await conn.exec_driver_sql(
            "ALTER TABLE seed_videos ADD COLUMN posted_at DATETIME"
        )
    if "platform" not in seed_cols:
        await conn.exec_driver_sql(
            "ALTER TABLE seed_videos ADD COLUMN platform TEXT DEFAULT 'tiktok'"
        )
    if "rating" not in seed_cols:
        await conn.exec_driver_sql(
            "ALTER TABLE seed_videos ADD COLUMN rating INTEGER"
        )
    if "gemini_analysis" not in seed_cols:
        await conn.exec_driver_sql(
            "ALTER TABLE seed_videos ADD COLUMN gemini_analysis TEXT"
        )

    # --- seed_videos: drop NOT NULL from view_count (needed for Instagram seeds) ---
    # SQLite can't ALTER COLUMN, so we do a table swap if view_count is still NOT NULL.
    result3 = await conn.exec_driver_sql("PRAGMA table_info(seed_videos)")
    seed_col_detail = {row[1]: row[3] for row in result3.fetchall()}  # name -> notnull
    if seed_col_detail.get("view_count") == 1:
        await conn.exec_driver_sql("""
            CREATE TABLE seed_videos_tmp (
                id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'tiktok',
                niche TEXT NOT NULL,
                view_count INTEGER,
                like_count INTEGER NOT NULL,
                rating INTEGER,
                gemini_analysis TEXT,
                performed BOOLEAN DEFAULT 0,
                notes TEXT,
                posted_at DATETIME,
                created_at DATETIME
            )
        """)
        await conn.exec_driver_sql(
            "INSERT INTO seed_videos_tmp "
            "SELECT id, filename, platform, niche, view_count, like_count, "
            "rating, gemini_analysis, performed, notes, posted_at, created_at "
            "FROM seed_videos"
        )
        await conn.exec_driver_sql("DROP TABLE seed_videos")
        await conn.exec_driver_sql("ALTER TABLE seed_videos_tmp RENAME TO seed_videos")

    # --- seed_videos: source/provenance (v1.20) — added AFTER the swap above so
    # the legacy table-rebuild can't drop it. "admin" default backfills old rows.
    result4 = await conn.exec_driver_sql("PRAGMA table_info(seed_videos)")
    seed_cols2 = {row[1] for row in result4.fetchall()}
    if "source" not in seed_cols2:
        await conn.exec_driver_sql(
            "ALTER TABLE seed_videos ADD COLUMN source TEXT DEFAULT 'admin'"
        )

    # --- user_analyses: platform column (default tiktok for existing rows) ---
    if "platform" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN platform TEXT DEFAULT 'tiktok'"
        )
    if "actual_likes" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN actual_likes INTEGER"
        )
    if "pending_seed_consent" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN pending_seed_consent BOOLEAN DEFAULT 0"
        )
    if "status" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN status TEXT DEFAULT 'complete'"
        )
    if "correction_json" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN correction_json TEXT"
        )
    # Build #3: calibration version stamped onto each prediction (0 = un-nudged).
    if "calibration_version" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN calibration_version INTEGER DEFAULT 0"
        )
    # Canonical niche (calibration keys on this, not the raw display niche).
    if "canonical_niche" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN canonical_niche TEXT"
        )
    # Re-analysis lineage: NULL = original; non-NULL = improved version of parent.
    if "parent_id" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN parent_id INTEGER"
        )

    # --- users: email auth + age gate + seed consent (v1.24) ---
    # NOTE: SQLite forbids adding a UNIQUE column via ALTER TABLE, so email
    # uniqueness on legacy SQLite DBs is enforced at the app layer (signup
    # checks). Fresh DBs get the real constraint from create_all.
    result5 = await conn.exec_driver_sql("PRAGMA table_info(users)")
    user_cols = {row[1] for row in result5.fetchall()}
    if "email" not in user_cols:
        await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN email TEXT")
    if "birth_year" not in user_cols:
        await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN birth_year INTEGER")
    if "birth_date" not in user_cols:
        await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN birth_date TEXT")
    if "seed_consent" not in user_cols:
        await conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN seed_consent TEXT DEFAULT 'ask'"
        )
    # email_verified: DEFAULT 1 grandfathers existing accounts as verified so
    # the new signup verification step can't lock anyone out.
    if "email_verified" not in user_cols:
        await conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 1"
        )
    # --- users: Stripe billing (CraftLint Pro) ---
    for col, ddl in (
        ("stripe_customer_id", "ALTER TABLE users ADD COLUMN stripe_customer_id TEXT"),
        ("stripe_subscription_id", "ALTER TABLE users ADD COLUMN stripe_subscription_id TEXT"),
        ("subscription_status", "ALTER TABLE users ADD COLUMN subscription_status TEXT"),
        ("subscription_current_period_end", "ALTER TABLE users ADD COLUMN subscription_current_period_end DATETIME"),
        (
            "subscription_cancel_at_period_end",
            "ALTER TABLE users ADD COLUMN subscription_cancel_at_period_end BOOLEAN NOT NULL DEFAULT 0",
        ),
        (
            "stripe_last_payment_action_id",
            "ALTER TABLE users ADD COLUMN stripe_last_payment_action_id TEXT",
        ),
    ):
        if col not in user_cols:
            await conn.exec_driver_sql(ddl)
    # Session epoch for token invalidation on password change/reset.
    if "token_version" not in user_cols:
        await conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"
        )

    # --- usage_events: served Gemini model version ---
    result6 = await conn.exec_driver_sql("PRAGMA table_info(usage_events)")
    usage_event_cols = {row[1] for row in result6.fetchall()}
    if "model_version" not in usage_event_cols:
        await conn.exec_driver_sql(
            "ALTER TABLE usage_events ADD COLUMN model_version TEXT"
        )


async def _ensure_columns_pg(conn):
    """Postgres self-migration (v1.21): additive-only, idempotent statements run on
    every boot. `ADD COLUMN IF NOT EXISTS` is a catalog no-op once applied, so the
    cost is microseconds per boot — and deploys become self-migrating (no manual
    Neon ALTER TABLE step).

    RULES for this list:
      - ADDITIVE ONLY: new nullable/defaulted columns. Never DROP / RENAME /
        ALTER TYPE here — destructive changes stay manual and deliberate.
      - Append, never reorder: each statement must stay valid forever against
        any historical schema state.
    `create_all` above handles brand-new TABLES; this handles new COLUMNS on
    existing tables (create_all never alters existing tables).
    """
    statements = [
        # --- user_analyses ---
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS user_id INTEGER",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS platform VARCHAR DEFAULT 'tiktok'",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS caption TEXT",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS bio TEXT",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS project_name VARCHAR",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS actual_likes INTEGER",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS mode VARCHAR DEFAULT 'quick'",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS video_url VARCHAR",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS counts_fetched_at TIMESTAMP",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS guest_claim_token VARCHAR",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS promoted_seed_id INTEGER",
        # --- seed_videos ---
        "ALTER TABLE seed_videos ADD COLUMN IF NOT EXISTS platform VARCHAR DEFAULT 'tiktok'",
        "ALTER TABLE seed_videos ADD COLUMN IF NOT EXISTS rating INTEGER",
        "ALTER TABLE seed_videos ADD COLUMN IF NOT EXISTS gemini_analysis TEXT",
        "ALTER TABLE seed_videos ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP",
        "ALTER TABLE seed_videos ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'admin'",
        # Instagram seeds have no public view count (no-op once already nullable)
        "ALTER TABLE seed_videos ALTER COLUMN view_count DROP NOT NULL",
        # --- v1.24: email auth + age gate + seed consent ---
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR UNIQUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_year INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS seed_consent VARCHAR DEFAULT 'ask'",
        # DEFAULT TRUE grandfathers existing accounts as verified.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT TRUE",
        # Stripe billing (CraftLint Pro). Written only by the verified webhook.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_current_period_end TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_last_payment_action_id VARCHAR",
        "CREATE INDEX IF NOT EXISTS ix_users_stripe_customer_id ON users (stripe_customer_id)",
        # Session epoch for token invalidation on password change/reset.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS pending_seed_consent BOOLEAN DEFAULT FALSE",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'complete'",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS correction_json TEXT",
        # Build #3: calibration version stamped onto each prediction (0 = un-nudged).
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS calibration_version INTEGER DEFAULT 0",
        # Canonical niche (calibration keys on this, not the raw display niche).
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS canonical_niche VARCHAR",
        # Re-analysis lineage: NULL = original; non-NULL = improved version of parent.
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS parent_id INTEGER",
        # Served model version exposes weight changes behind Gemini's moving alias.
        "ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS model_version VARCHAR",
        # Dedup: if any email appears more than once (case-insensitive), null out all
        # but the newest account (highest id). Idempotent — no-op when no duplicates.
        "UPDATE users SET email = NULL WHERE email IS NOT NULL AND id NOT IN (SELECT MAX(id) FROM users WHERE email IS NOT NULL GROUP BY lower(email))",
        # Enforce case-insensitive uniqueness on email. Partial index (WHERE email IS
        # NOT NULL) lets legacy accounts keep NULL without conflicting. Idempotent via
        # IF NOT EXISTS. Works even if ADD COLUMN UNIQUE above was already applied.
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_ci ON users (lower(email)) WHERE email IS NOT NULL",
    ]
    for stmt in statements:
        await conn.exec_driver_sql(stmt)


def _assert_prod_secrets() -> None:
    """Refuse to boot in production with insecure development defaults.

    Prod is detected by DATABASE_URL being set (Neon); local dev defaults to
    SQLite and is exempt. A default JWT_SECRET lets anyone forge a token for any
    user; the default ADMIN_PASSWORD is documented publicly. Failing loudly here
    turns a silent account-takeover hole into an obvious failed deploy.
    """
    if not os.getenv("DATABASE_URL"):
        return  # local / dev — the dev defaults are fine
    insecure = []
    if os.getenv("JWT_SECRET", "") in ("", "dev-insecure-secret-change-me"):
        insecure.append("JWT_SECRET")
    if os.getenv("ADMIN_PASSWORD", "") in ("", "viraliq-admin"):
        insecure.append("ADMIN_PASSWORD")
    if insecure:
        raise RuntimeError(
            "Refusing to start in production with insecure default(s): "
            + ", ".join(insecure)
            + ". Set each to a strong, unique value in the Railway environment."
        )


import logging as _logging
_boot_logger = _logging.getLogger("surge.boot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _assert_prod_secrets()
    if not os.getenv("SMTP_USER") or not os.getenv("SMTP_PASS"):
        _boot_logger.warning(
            "SMTP NOT CONFIGURED — forgot-password and welcome emails will NOT send. "
            "Add SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / EMAIL_FROM to Railway env vars."
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # _ensure_columns uses SQLite-only PRAGMA syntax; _ensure_columns_pg is
        # its Postgres twin. Together: every deploy migrates its own schema.
        if engine.dialect.name == "sqlite":
            await _ensure_columns(conn)
        else:
            await _ensure_columns_pg(conn)
    from services.scheduler import start as start_scheduler, stop as stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()


class SecurityHeadersMiddleware:
    """Attach defense-in-depth response headers on every request. Pure ASGI (no
    per-request task wrapper, unlike BaseHTTPMiddleware) so it adds negligible
    overhead and doesn't interfere with streaming or BackgroundTasks. Cheap + safe
    for a JSON API: nosniff blocks content-type confusion, DENY blocks framing
    (clickjacking), and the referrer policy avoids leaking full URLs cross-origin."""

    _HEADERS = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
    )

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message.setdefault("headers", []))
                for key, value in self._HEADERS:
                    if key.decode() not in headers:
                        headers.append(key.decode(), value.decode())
            await send(message)

        await self.app(scope, receive, send_wrapper)


app = FastAPI(title="CraftLint API", lifespan=lifespan)

# Compress JSON/text responses on the wire. Analysis payloads (scores_json with
# the full critique + improvement plan) are ~8–20 KB of highly repetitive JSON;
# gzip cuts that ~70–80%, so it's the single biggest win for response latency on
# slow/mobile connections. minimum_size skips tiny bodies where the gzip header
# would cost more than it saves. Added BEFORE CORS so CORS stays the outermost
# layer and still attaches its headers to the (now compressed) response.
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

# Defense-in-depth security headers. Added between GZip and CORS so CORS remains
# the outermost layer (its headers still attach and preflight is handled first).
app.add_middleware(SecurityHeadersMiddleware)

# Comma-separated origins from env, e.g. "http://localhost:3000,https://viraliq.vercel.app"
_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [o.strip() for o in _origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(analyze_router)
app.include_router(billing_router)
app.include_router(profile_router)
app.include_router(settings_router)


# Accept HEAD as well as GET: UptimeRobot (and many uptime probes) default to
# HEAD requests, and FastAPI's @app.get does not auto-add HEAD, which would
# otherwise return 405 Method Not Allowed and trip a false "down" incident.
@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok"}


# Coarse, unauthenticated collector health for uptime monitors. A 100%-failing
# outcome collector was previously indistinguishable from "nothing was due"; a
# monitor can now alert when status becomes "failing". Provider names and per-job
# detail are withheld here (see the authenticated admin route for the full view).
@app.get("/health/collectors")
async def health_collectors():
    from database import AsyncSessionLocal
    from services.outcome_collection import collector_health
    async with AsyncSessionLocal() as db:
        health = await collector_health(db)
    return {
        "status": health["status"],
        "window_days": health["window_days"],
        "fetch_attempts": health["fetch_attempts"],
        "fetch_successful": health["fetch_successful"],
        "fetch_failure_ratio": health["fetch_failure_ratio"],
        "last_run_incident": (health.get("last_run") or {}).get("incident"),
    }
