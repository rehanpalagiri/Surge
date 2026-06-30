"""Per-user analysis allowance.

Tiers (chosen 2026-06-30):
  • Surge Pro  → UNLIMITED analyses.
  • Free       → 3 analyses per CALENDAR MONTH (UTC), resetting on the 1st.

Bonus credits (both tiers retain the engagement loop, though it's moot for Pro):
  +1 per all-time UNIQUE verified linked post (video_url AND counts_fetched_at
  set = the provider confirmed it was live), capped at +10. Counted by unique
  normalized post id, so one video linked to several projects yields one credit.

Only authenticated users are metered here; guests are gated by the in-memory
guest throttle in routers/analyze.py. Failed analyses (status="error") never
consume the allowance.
"""
from datetime import datetime
from urllib.parse import urlsplit

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from auth import is_pro
from models import User, UserAnalysis
from services.clock import utc_now_naive
from services.outcomes import post_id_from_url

FREE_MONTHLY_LIMIT = 3
MAX_BONUS = 10


def _normalize_video_url(url: str) -> str:
    """Collapse trivial variants of the same posted video (scheme, www,
    query string, fragment, trailing slash) so one video linked to multiple
    projects can't farm multiple bonus credits."""
    try:
        parts = urlsplit(url.strip())
        host = parts.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = parts.path.rstrip("/")
        return f"{host}{path}"
    except Exception:
        return url.strip().lower()


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month_start(now: datetime) -> datetime:
    if now.month == 12:
        return now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


async def _bonus_credits(user_id: int, db: AsyncSession) -> int:
    """All-time unique verified linked posts, capped at MAX_BONUS."""
    links_q = await db.execute(
        select(UserAnalysis.video_url, UserAnalysis.platform).where(
            UserAnalysis.user_id == user_id,
            UserAnalysis.video_url.isnot(None),
            UserAnalysis.counts_fetched_at.isnot(None),
        )
    )
    unique_links = set()
    for url, platform in links_q.all():
        if not url:
            continue
        platform = platform or "tiktok"
        post_id = post_id_from_url(url, platform)
        unique_links.add(f"{platform}:{post_id}" if post_id else _normalize_video_url(url))
    return min(len(unique_links), MAX_BONUS)


async def get_rate_limit(user: User, db: AsyncSession) -> dict:
    """Return the full allowance status for a user.

    Keys: allowed, tier ("free"|"pro"), unlimited, used (this month),
    base_limit, bonus, effective_limit, remaining, resets_at (ISO, None for Pro),
    period ("month"). For Pro, limit/remaining/resets_at are None (unlimited).
    """
    now = utc_now_naive()
    consumes_credit = or_(
        UserAnalysis.status.is_(None),
        UserAnalysis.status != "error",
    )
    month_start = _month_start(now)

    # Analyses consumed this calendar month. Failed async analyses are excluded so
    # users are not charged for a report they never received; active rows still
    # count so repeated pending jobs can't bypass the cap.
    used_q = await db.execute(
        select(func.count()).select_from(UserAnalysis).where(
            UserAnalysis.user_id == user.id,
            UserAnalysis.created_at >= month_start,
            consumes_credit,
        )
    )
    used: int = used_q.scalar() or 0

    bonus = await _bonus_credits(user.id, db)

    if is_pro(user):
        return {
            "allowed": True,
            "tier": "pro",
            "unlimited": True,
            "used": used,
            "base_limit": None,
            "bonus": bonus,
            "effective_limit": None,
            "remaining": None,
            "resets_at": None,
            "period": "month",
        }

    effective_limit = FREE_MONTHLY_LIMIT + bonus
    return {
        "allowed": used < effective_limit,
        "tier": "free",
        "unlimited": False,
        "used": used,
        "base_limit": FREE_MONTHLY_LIMIT,
        "bonus": bonus,
        "effective_limit": effective_limit,
        "remaining": max(0, effective_limit - used),
        "resets_at": _next_month_start(now).isoformat(),
        "period": "month",
    }
