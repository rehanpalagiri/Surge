"""Daily outcome-collection scheduler + weekly admin-seed niche synthesis.

Runs once per day at 06:00 UTC inside the FastAPI process so no external
cron service is required. Calls collect_due_outcomes() which processes all
pending maturity-window jobs (24h / 7d / 30d) that are currently due.

Also runs a weekly job (Monday 07:00 UTC, after the daily collection) that
regenerates niche_insights/trend_summaries from the admin seed pool — see
services/niche_synthesis.py. Gated by NICHE_SYNTHESIS_ENABLED (default OFF); the
job is a no-op until an operator turns that on.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.niche_synthesis import run_weekly_niche_synthesis
from services.outcome_collection import collect_due_outcomes, summarize_run

logger = logging.getLogger("surge.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _run_daily_collection() -> None:
    logger.info("Scheduler: starting daily outcome collection")
    try:
        result = await collect_due_outcomes(limit=100)
        # summarize_run stashes the run for /health/collectors and ERROR-logs a
        # high-failure run so a 100%-failing collector can't hide as a quiet INFO.
        summary = summarize_run(result)
        logger.info("Scheduler: collection complete — %s", summary)
    except Exception as exc:
        logger.error("Scheduler: collection crashed — %s: %s", type(exc).__name__, exc)


async def _run_weekly_niche_synthesis() -> None:
    logger.info("Scheduler: starting weekly niche synthesis")
    try:
        result = await run_weekly_niche_synthesis()
        logger.info("Scheduler: niche synthesis complete — %s", result.get("status"))
    except Exception as exc:
        logger.error("Scheduler: niche synthesis crashed — %s: %s", type(exc).__name__, exc)


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
    _scheduler.add_job(
        _run_weekly_niche_synthesis,
        trigger=CronTrigger(day_of_week="mon", hour=7, minute=0, timezone="UTC"),
        id="weekly_niche_synthesis",
        name="Weekly admin-seed niche + trend synthesis",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600 * 6,  # weekly cadence — generous catch-up window
    )
    _scheduler.start()
    logger.info("Scheduler: started — daily outcome collection at 06:00 UTC, weekly niche synthesis Mondays 07:00 UTC")
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler: stopped")
    _scheduler = None
