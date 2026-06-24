"""
Rolling-window upload rate limiter.

Free tier: 10 uploads per 3-hour window.
Bonus credits: +1 per all-time verified linked video (video_url set AND
counts_fetched_at set = tikwm confirmed it was live), capped at +10.
Counted by UNIQUE normalized URL, so the same video linked to multiple
projects yields only one bonus credit.
Max possible: 20 per 3-hour window for users who always link their posts.

Only applies to authenticated users — guests are unmetered (they can't
link videos anyway and their analyses are not tied to an account).
"""
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import UserAnalysis
from services.outcomes import post_id_from_url

WINDOW_HOURS = 3
BASE_LIMIT = 10
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
        # Provider post IDs and Instagram shortcodes may be case-sensitive.
        path = parts.path.rstrip("/")
        return f"{host}{path}"
    except Exception:
        return url.strip().lower()


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

    # Bonus: all-time UNIQUE verified links (video_url set AND counts_fetched_at set).
    # Count distinct NORMALIZED URLs, not rows — the same posted video linked to
    # multiple projects must not farm multiple bonus credits.
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
    bonus: int = min(len(unique_links), MAX_BONUS)

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
