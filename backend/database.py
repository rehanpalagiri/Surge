import os
import ssl
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
import certifi

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# ─────────────────────────────────────────────────────────────────────────────
# Local dev default: SQLite file in the repo root (zero config).
# In production (Render), set DATABASE_URL to a Neon direct connection string:
#   postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/dbname?sslmode=require
#
# IMPORTANT Neon / asyncpg quirks handled below:
#   1. Scheme normalisation  — postgres:// / postgresql:// → postgresql+asyncpg://
#   2. SSL                   — asyncpg needs ssl via connect_args, NOT ?sslmode=…
#                              Strip sslmode & channel_binding from the query string
#                              and pass an ssl.SSLContext instead.
#   3. Pooled vs direct URL  — Use the DIRECT (non-pooler) URL on Render; it's a
#                              long-lived process and direct connections are faster.
#                              If you must use a -pooler URL (pgbouncer), set
#                              statement_cache_size=0 — pgbouncer rejects prepared
#                              statements which asyncpg uses by default.
# ─────────────────────────────────────────────────────────────────────────────

_RAW_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./viraliq.db")


def _build_engine(raw_url: str):
    # ── SQLite (local dev) ────────────────────────────────────────────────────
    if raw_url.startswith("sqlite"):
        return create_async_engine(raw_url, echo=False)

    # ── Postgres ──────────────────────────────────────────────────────────────
    url = raw_url

    # 1. Normalise scheme → postgresql+asyncpg://
    for old_prefix in ("postgres://", "postgresql://"):
        if url.startswith(old_prefix):
            url = "postgresql+asyncpg://" + url[len(old_prefix):]
            break

    # 2. Strip query params that asyncpg / SQLAlchemy don't understand
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs.pop("sslmode", None)
    qs.pop("channel_binding", None)
    clean_query = urlencode({k: v[0] for k, v in qs.items()})
    clean_url = urlunparse(parsed._replace(query=clean_query))

    # 3. asyncpg TLS must go through connect_args, not the URL.
    #    Use certifi's CA bundle — works on macOS (Python from python.org doesn't
    #    trust the system keychain) and on Linux/Render equally well.
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connect_args: dict = {"ssl": ssl_ctx}

    # 4. pgbouncer (pooler URLs) doesn't support prepared statements
    if "-pooler" in raw_url:
        connect_args["statement_cache_size"] = 0

    return create_async_engine(clean_url, echo=False, connect_args=connect_args)


engine = _build_engine(_RAW_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
