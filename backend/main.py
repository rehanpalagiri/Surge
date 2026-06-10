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


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # _ensure_columns uses SQLite-only PRAGMA syntax — skip on Postgres.
        # On a fresh Postgres DB, create_all above already creates every column
        # from the model definition, so the shim is unnecessary there.
        if engine.dialect.name == "sqlite":
            await _ensure_columns(conn)
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
