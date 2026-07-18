"""Per-user analysis allowance.

Tiers (chosen 2026-06-30):
  • CraftLint Pro  → UNLIMITED analyses.
  • Free       → 3 analyses per CALENDAR MONTH (UTC), resetting on the 1st.

Bonus credits (both tiers retain the engagement loop, though it's moot for Pro):
  +1 per all-time UNIQUE verified linked post (video_url AND counts_fetched_at
  set = the provider confirmed it was live), capped at +2. Counted by unique
  normalized post id, so one video linked to several projects yields one credit.

Only authenticated users are metered here; guests are gated by the in-memory
guest throttle in routers/analyze.py. Failed analyses (status="error") never
consume the allowance.

Pro is monthly-unlimited but carries a SOFT DAILY fair-use ceiling: at
~1.5–3¢/analysis, a 30+/day agency seat would run the Gemini bill underwater on a
$9.99/mo flat price. The ceiling only bites at agency-scale abuse; a normal Pro
creator never approaches it, and it resets every UTC day.

Pro also carries a rolling 5-hour cost-window cap (services/cost_window.py),
independent of the daily fair-use count above — see that module's docstring.
It bounds actual estimated spend rather than analysis count, which matters once
per-analysis cost varies by provider mix.
"""
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from auth import is_pro
from models import User, UserAnalysis
from services.clock import utc_now_naive
from services.cost_window import get_cost_window_status, PRO_COST_WINDOW_HOURS
from services.outcomes import post_id_from_url

FREE_MONTHLY_LIMIT = 3
MAX_BONUS = 2
# Soft daily fair-use ceiling on "unlimited" Pro. Chosen so a normal creator never
# hits it while an agency running dozens/day (which would make the flat price
# unprofitable) is throttled to a sustainable rate. Resets at 00:00 UTC.
PRO_FAIR_USE_DAILY = 15


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


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _next_day_start(now: datetime) -> datetime:
    return _day_start(now) + timedelta(days=1)


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
        # Monthly is unlimited, but a soft daily fair-use ceiling protects unit
        # economics. Only today's (UTC) successful/active analyses count toward it;
        # failed rows are excluded exactly like the free tier.
        day_start = _day_start(now)
        used_today = (await db.execute(
            select(func.count()).select_from(UserAnalysis).where(
                UserAnalysis.user_id == user.id,
                UserAnalysis.created_at >= day_start,
                consumes_credit,
            )
        )).scalar() or 0
        within_fair_use = used_today < PRO_FAIR_USE_DAILY
        # Skip the cost-window query entirely once fair-use already blocks — the
        # overall "allowed" is False either way, so the extra join+sum would be
        # wasted work on exactly the requests hitting this path most (an
        # already-throttled agency-scale seat retrying).
        cost_window = await get_cost_window_status(user.id, db) if within_fair_use else None

        limit_reason = None
        if not within_fair_use:
            limit_reason = "fair_use"
        elif not cost_window["allowed"]:
            limit_reason = "cost_window"

        return {
            "allowed": within_fair_use and (cost_window is None or cost_window["allowed"]),
            "tier": "pro",
            "unlimited": True,
            "used": used,
            "base_limit": None,
            "bonus": bonus,
            "effective_limit": None,
            "remaining": None,
            "resets_at": None,
            "period": "month",
            # Fair-use (Pro only): daily soft ceiling status.
            "fair_use_daily_limit": PRO_FAIR_USE_DAILY,
            "used_today": used_today,
            "fair_use_remaining": max(0, PRO_FAIR_USE_DAILY - used_today),
            "fair_use_resets_at": _next_day_start(now).isoformat(),
            # Rolling 5-hour cost-window (Pro only): estimated-spend ceiling status.
            # None for used/budget when already blocked by fair-use above — not
            # queried in that case (see the skip comment near cost_window).
            "cost_window_hours": PRO_COST_WINDOW_HOURS,
            "cost_window_used_micros": cost_window["used_micros"] if cost_window else None,
            "cost_window_budget_micros": cost_window["budget_micros"] if cost_window else None,
            "limit_reason": limit_reason,
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
