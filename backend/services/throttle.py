"""Durable, cross-process sliding-window throttle for abuse-sensitive auth/upload
endpoints, backed by the ``rate_limit_hits`` table.

Previously in-memory (a per-process ``deque``), which is why the Dockerfile pinned
``WEB_CONCURRENCY=1``: a second worker kept its own counters and each granted the
full quota. Storing hits in the shared DB makes every limit hold across workers and
replicas, so a horizontally scaled deployment enforces the same caps.

Tradeoff: this adds a few small queries to the primary DB — the same layer that is
the measured throughput bottleneck. It's acceptable here because every throttled
endpoint (auth, password reset, guest upload) is LOW VOLUME. For serious horizontal
scale, move this to Redis (``INCR`` + ``EXPIRE``, or a sorted-set sliding window) to
keep the load off the primary DB entirely.

This is NOT the analysis allowance (services/rate_limit.py); it is purely a
brute-force / spam guard on the unauthenticated auth + guest-upload endpoints.
"""
import os
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import RateLimitHit
from services.clock import utc_now_naive

# How many proxy hops in front of the app we control and therefore trust.
# Railway routes every request through exactly ONE edge proxy (Envoy), which
# appends the real downstream peer as the LAST X-Forwarded-For entry, so the
# default of 1 means "trust only the rightmost entry". Raise this only if you
# add more trusted reverse proxies in front of Railway.
_TRUSTED_PROXY_HOPS = max(1, int(os.getenv("TRUSTED_PROXY_HOPS", "1")))


def client_ip(request) -> str:
    """Resolve the real client IP for rate-limiting / abuse keys.

    SECURITY: ``X-Forwarded-For`` is a comma list ``client, proxy1, proxy2, …``
    where the LEFT entries are supplied by the caller and are fully spoofable —
    keying a throttle on ``xff.split(',')[0]`` lets anyone mint an unlimited
    supply of fresh rate-limit buckets just by varying the header, defeating
    every per-IP guard (guest analysis cap, upload cap, password-reset and
    email-verify brute-force limits).

    We instead trust only the rightmost ``TRUSTED_PROXY_HOPS`` entries — the
    ones appended by infrastructure we control — and return the IP the
    outermost trusted proxy actually observed. On Railway (1 hop) that's the
    last entry, which a spoofer can only push further left, never overwrite.
    Falls back to the socket peer when no forwarding header is present (local
    dev / direct connections).
    """
    xff = request.headers.get("x-forwarded-for", "") or ""
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if parts:
        idx = min(len(parts), _TRUSTED_PROXY_HOPS)
        return parts[-idx]
    return request.client.host if request.client else "unknown"


# Sweep of abandoned keys: per-call cleanup below already removes a key's own
# expired rows, so the table only accumulates rows for keys that are never queried
# again. Every _SWEEP_EVERY calls we bulk-delete anything past the longest window.
# The counter is a per-process heuristic (no cross-process coordination needed —
# the sweep is pure garbage collection, not correctness).
_calls = 0
_SWEEP_EVERY = 5000          # bulk-purge idle keys every N calls to bound the table
_MAX_WINDOW = 3600           # longest window any caller uses (seconds)


async def check_rate(
    db: AsyncSession, key: str, max_hits: int, window_seconds: int
) -> bool:
    """Record a hit for ``key`` and return True if it's within the limit.

    Durable sliding window shared across all workers: drop this key's hits older
    than ``window_seconds``, count what remains, and insert a new hit only when it
    is still under ``max_hits`` (returning False without inserting otherwise). Uses
    wall-clock UTC — the persisted, cross-process clock — instead of the old
    monotonic clock, which can't be shared or stored.

    Uses the caller's request session and COMMITS immediately, so the hit is durable
    regardless of how the request ends. Every call site invokes this before any other
    write in the handler, so the commit never flushes unrelated pending changes.

    Note: the delete → count → insert isn't locked, so under heavy concurrency two
    workers can each admit the "last" hit and briefly exceed the cap by one. That is
    acceptable for a brute-force guard (the cap is approximate by design); it is not
    a fund/quota ledger.
    """
    global _calls
    now = utc_now_naive()
    cutoff = now - timedelta(seconds=window_seconds)

    # Drop this key's expired hits, then count what's left inside the window.
    await db.execute(
        delete(RateLimitHit).where(
            RateLimitHit.key == key, RateLimitHit.hit_at < cutoff
        )
    )
    count = (
        await db.execute(
            select(func.count())
            .select_from(RateLimitHit)
            .where(RateLimitHit.key == key)
        )
    ).scalar() or 0

    _calls += 1
    if _calls % _SWEEP_EVERY == 0:
        await db.execute(
            delete(RateLimitHit).where(
                RateLimitHit.hit_at < now - timedelta(seconds=_MAX_WINDOW)
            )
        )

    allowed = count < max_hits
    if allowed:
        db.add(RateLimitHit(key=key, hit_at=now))
    # Commit either way: persist the expired-row cleanup (and the new hit when
    # allowed). The rejection path still commits so the sweep/cleanup isn't lost.
    await db.commit()
    return allowed
