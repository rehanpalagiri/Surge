"""Rolling 5-hour spend cap for CraftLint Pro — bounds cost exposure once the
Pro tier stops being effectively free to run "unlimited" (see updates.md's
"Billing & rate limiting" note before this shipped).

Continuous trailing-window, not a discrete session bucket: on every check we sum
``usage_events.estimated_cost_micros`` for this user's analyses over the trailing
``PRO_COST_WINDOW_HOURS`` and compare to budget. Stateless and read-only — reuses
the existing usage_events ledger as sole source of truth (same query shape as
services/throttle.py's sliding-window check_rate, joined through UserAnalysis
since usage_events has no user_id column of its own). No new table, no write-hook
in services/gemini.py.

This is scoped to the Pro tier only — never called for free-tier users, so it is
never stacked on the free tier's separate monthly-count limiter
(services/rate_limit.py).

Race note (same tradeoff services/throttle.py's check_rate documents for its own
sliding window): this is a read-only gate, not a reservation — a burst of N
concurrent requests from one user can all read the same pre-burst sum and all
pass, since actual cost is only known and written after each Gemini call
completes (see services/telemetry.py). Acceptable for a launch-time, generous,
per-account cost ceiling; not a hard financial guarantee. Revisit (e.g. a
locked reservation) if real abuse patterns show concurrent bursts matter.
"""
import os
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import UsageEvent, UserAnalysis
from services.clock import utc_now_naive

PRO_COST_WINDOW_HOURS = 5
# Launch-time guess, not tuned against real spend data yet (none exists pre-launch).
# Ship generous; revisit the number once real telemetry exists. Overridable without
# a redeploy via PRO_COST_WINDOW_BUDGET_USD, same override pattern as
# services/telemetry.py's GEMINI_FLASH_*_PRICE_PER_MTOK.
_DEFAULT_BUDGET_USD = 1.00


def _budget_micros() -> int:
    raw = os.getenv("PRO_COST_WINDOW_BUDGET_USD")
    if raw:
        try:
            parsed = float(raw)
            # A non-positive override would permanently block every Pro request
            # (used_micros < 0 is never true), which is never an intended config —
            # treat it as unset rather than silently locking out the whole tier.
            if parsed > 0:
                return round(parsed * 1_000_000)
        except ValueError:
            pass
    return round(_DEFAULT_BUDGET_USD * 1_000_000)


async def get_cost_window_status(user_id: int, db: AsyncSession) -> dict:
    """Trailing PRO_COST_WINDOW_HOURS estimated spend for this user, in micros.

    NULL ``estimated_cost_micros`` (failed calls without measured token counts)
    are ignored by SUM, same NULL-handling as services/economics.py. Usage events
    with no analysis_id (untied to any analysis) are dropped by the inner join —
    they can't be attributed to a user.
    """
    cutoff = utc_now_naive() - timedelta(hours=PRO_COST_WINDOW_HOURS)
    stmt = (
        select(func.coalesce(func.sum(UsageEvent.estimated_cost_micros), 0))
        .select_from(UsageEvent)
        .join(UserAnalysis, UserAnalysis.id == UsageEvent.analysis_id)
        .where(UserAnalysis.user_id == user_id, UsageEvent.created_at >= cutoff)
    )
    used_micros = int((await db.execute(stmt)).scalar() or 0)
    budget_micros = _budget_micros()
    return {
        "allowed": used_micros < budget_micros,
        "used_micros": used_micros,
        "budget_micros": budget_micros,
        "window_hours": PRO_COST_WINDOW_HOURS,
    }
