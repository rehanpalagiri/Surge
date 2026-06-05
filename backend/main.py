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

    # --- seed_videos ---
    result = await conn.exec_driver_sql("PRAGMA table_info(seed_videos)")
    seed_cols = {row[1] for row in result.fetchall()}
    if "posted_at" not in seed_cols:
        await conn.exec_driver_sql(
            "ALTER TABLE seed_videos ADD COLUMN posted_at DATETIME"
        )

    # --- user_analyses: platform column (default tiktok for existing rows) ---
    if "platform" not in existing:
        await conn.exec_driver_sql(
            "ALTER TABLE user_analyses ADD COLUMN platform TEXT DEFAULT 'tiktok'"
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


app = FastAPI(title="ViralIQ API", lifespan=lifespan)

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


@app.get("/health")
async def health():
    return {"status": "ok"}
