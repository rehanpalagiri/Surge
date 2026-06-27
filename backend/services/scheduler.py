"""Daily outcome-collection scheduler.

Runs once per day at 06:00 UTC inside the FastAPI process so no external
cron service is required. Calls collect_due_outcomes() which processes all
pending maturity-window jobs (24h / 7d / 30d) that are currently due.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.outcome_collection import collect_due_outcomes

logger = logging.getLogger("surge.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _run_daily_collection() -> None:
    logger.info("Scheduler: starting daily outcome collection")
    try:
        result = await collect_due_outcomes(limit=100)
        logger.info("Scheduler: collection complete — %s", result)
    except Exception as exc:
        logger.error("Scheduler: collection failed — %s: %s", type(exc).__name__, exc)


def start() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_daily_collection,
        trigger=CronTrigger(hour=6, minute=0, timezone="UTC"),
        id="daily_outcome_collection",
        name="Daily outcome collection (24h/7d/30d windows)",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,  # if the server was down, run within 1h of 06:00
    )
    _scheduler.start()
    logger.info("Scheduler: started — daily outcome collection at 06:00 UTC")
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler: stopped")
    _scheduler = None
