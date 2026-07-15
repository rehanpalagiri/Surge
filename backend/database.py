import os
import ssl
import certifi

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# ─────────────────────────────────────────────────────────────────────────────
# Local dev default: SQLite file in the repo root (zero config).
# In production, set DATABASE_URL to a Neon direct connection string:
#   postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/dbname?sslmode=require
#
# IMPORTANT Neon / asyncpg quirks handled below:
#   1. Scheme normalisation  — postgres:// / postgresql:// → postgresql+asyncpg://
#   2. SSL                   — asyncpg needs ssl via connect_args, NOT ?sslmode=…
#                              Strip sslmode & channel_binding from the query string
#                              and pass an ssl.SSLContext instead.
#   3. Pooled vs direct URL  — Use the DIRECT (non-pooler) URL; it's a long-lived
#                              process. If you must use a -pooler URL (pgbouncer),
#                              set statement_cache_size=0.
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

    # 2. Use SQLAlchemy's URL parser (handles special chars in passwords safely)
    #    then strip query params asyncpg doesn't understand.
    parsed = make_url(url)
    clean_query = {k: v for k, v in parsed.query.items()
                   if k not in ("sslmode", "channel_binding")}
    clean = parsed.set(query=clean_query)

    # 3. asyncpg TLS must go through connect_args, not the URL.
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connect_args: dict = {"ssl": ssl_ctx}

    # 4. pgbouncer (pooler URLs) doesn't support prepared statements
    if "-pooler" in raw_url:
        connect_args["statement_cache_size"] = 0

    return create_async_engine(
        clean,
        echo=False,
        connect_args=connect_args,
        pool_pre_ping=True,   # re-validate connections before use; drops dead ones
        pool_recycle=300,     # recycle after 5 min — before Neon's idle timeout closes them
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


engine = _build_engine(_RAW_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
