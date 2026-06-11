"""
Rolling-window upload rate limiter.

Free tier: 10 uploads per 3-hour window.
Bonus credits: +1 per all-time verified linked video (video_url set AND
counts_fetched_at set = tikwm confirmed it was live), capped at +10.
Max possible: 20 per 3-hour window for users who always link their posts.

Only applies to authenticated users — guests are unmetered (they can't
link videos anyway and their analyses are not tied to an account).
"""
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import UserAnalysis

WINDOW_HOURS = 3
BASE_LIMIT = 10
MAX_BONUS = 10


async def get_rate_limit(user_id: int, db: AsyncSession) -> dict:
    """Return the full rate limit status for a user.

    Returns a dict with:
      allowed      — bool, whether a new upload is permitted
      used         — uploads in the current window
      base_limit   — always BASE_LIMIT
      bonus        — verified-link bonus credits (0–MAX_BONUS)
      effective_limit — base_limit + bonus
      remaining    — effective_limit - used (floored at 0)
      resets_at    — ISO timestamp when the oldest in-window upload falls off
                     (None if window is empty)
      window_hours — always WINDOW_HOURS
    """
    window_start = datetime.utcnow() - timedelta(hours=WINDOW_HOURS)

    # Uploads consumed in current window
    used_q = await db.execute(
        select(func.count()).select_from(UserAnalysis).where(
            UserAnalysis.user_id == user_id,
            UserAnalysis.created_at >= window_start,
        )
    )
    used: int = used_q.scalar() or 0

    # Bonus: all-time verified links (video_url set AND counts_fetched_at set)
    bonus_q = await db.execute(
        select(func.count()).select_from(UserAnalysis).where(
            UserAnalysis.user_id == user_id,
            UserAnalysis.video_url.isnot(None),
            UserAnalysis.counts_fetched_at.isnot(None),
        )
    )
    bonus: int = min(bonus_q.scalar() or 0, MAX_BONUS)

    effective_limit = BASE_LIMIT + bonus

    # When does the oldest in-window upload fall off?
    oldest_q = await db.execute(
        select(UserAnalysis.created_at).where(
            UserAnalysis.user_id == user_id,
            UserAnalysis.created_at >= window_start,
        ).order_by(UserAnalysis.created_at.asc()).limit(1)
    )
    oldest = oldest_q.scalar()
    resets_at = (oldest + timedelta(hours=WINDOW_HOURS)).isoformat() if oldest else None

    return {
        "allowed": used < effective_limit,
        "used": used,
        "base_limit": BASE_LIMIT,
        "bonus": bonus,
        "effective_limit": effective_limit,
        "remaining": max(0, effective_limit - used),
        "resets_at": resets_at,
        "window_hours": WINDOW_HOURS,
    }
