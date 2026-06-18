import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine
from models import Base
from routers.admin import router as admin_router
from routers.analyze import router as analyze_router
from routers.auth import router as auth_router
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
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS actual_likes INTEGER",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS mode VARCHAR DEFAULT 'quick'",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS video_url VARCHAR",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS counts_fetched_at TIMESTAMP",
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
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS pending_seed_consent BOOLEAN DEFAULT FALSE",
        "ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'complete'",
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _assert_prod_secrets()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # _ensure_columns uses SQLite-only PRAGMA syntax; _ensure_columns_pg is
        # its Postgres twin. Together: every deploy migrates its own schema.
        if engine.dialect.name == "sqlite":
            await _ensure_columns(conn)
        else:
            await _ensure_columns_pg(conn)
    yield


app = FastAPI(title="Surge API", lifespan=lifespan)

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
app.include_router(profile_router)
app.include_router(settings_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
