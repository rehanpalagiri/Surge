"""Weekly admin-seed niche + trend synthesis, driven by services/scheduler.py.

Regenerates services.seed_insights.generate_niche_insight and
services.trend_insights.generate_trend_insight for every (platform, niche) pair
with enough seed data, storing results in the existing niche_insights /
trend_summaries tables — the same tables and shape the admin dashboard already
reads via routers/admin.py's manual /insights/generate and /trends/generate
endpoints. The only thing new here is the cadence (automatic, weekly) and the
consumer (also injected into the live reasoning pass — see
services.gemini.load_niche_synthesis_block).

Gated by NICHE_SYNTHESIS_ENABLED (default OFF). The generation functions
themselves work regardless of the flag (so the admin manual-trigger endpoints keep
working unchanged); this flag specifically gates (a) the automatic weekly run below
and (b) the grade-time read in services/gemini.py, so a fresh deploy stays blind to
seed-derived patterns — same shape as CLAUDE.md's SURGE_CALIBRATION_ENABLED gate —
until an operator explicitly turns this on.
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict

from sqlalchemy import select

from database import AsyncSessionLocal
from models import NicheInsight, SeedVideo, TrendSummary
from services.clock import utc_now_naive
from services.claude_client import claude_configured
from services.seed_insights import generate_niche_insight
from services.trend_insights import RECENT_WINDOW_DAYS, count_recent_established, generate_trend_insight

log = logging.getLogger("niche_synthesis")

_PLATFORMS = ("tiktok", "instagram")


def niche_synthesis_enabled() -> bool:
    """Master switch for the weekly admin-seed synthesis → live-grading injection
    path. Read at call time (not import), matching services.calibration's pattern,
    so nothing here can influence a live craft score unless an operator explicitly
    enables it."""
    return os.getenv("NICHE_SYNTHESIS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


async def _upsert(db, model, platform: str, niche: str, fields: dict) -> None:
    """Update-if-exists / insert-if-not for a (platform, niche)-unique row, shared by
    NicheInsight and TrendSummary. Rolls back on a failed commit so a concurrent
    writer racing the same row's UniqueConstraint (e.g. an admin manual trigger
    overlapping the weekly scheduler run) can't leave the shared session used by the
    REST of run_weekly_niche_synthesis's (platform, niche) loop in a
    failed-transaction state."""
    existing = (await db.execute(
        select(model).where(model.platform == platform, model.niche == niche)
    )).scalar_one_or_none()
    row = existing or model(platform=platform, niche=niche)
    for key, value in fields.items():
        setattr(row, key, value)
    row.generated_at = utc_now_naive()
    if existing is None:
        db.add(row)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def _synthesize_one(db, platform: str, niche: str, seeds: list) -> dict:
    result = {"platform": platform, "niche": niche, "seed_count": len(seeds)}
    try:
        insight_text = await generate_niche_insight(seeds, platform, niche)
        await _upsert(db, NicheInsight, platform, niche, {
            "insight": insight_text, "seed_count": len(seeds),
        })
        result["insight"] = "generated"
    except ValueError as e:
        result["insight"] = "skipped"
        result["insight_reason"] = str(e)
    except Exception as e:  # noqa: BLE001 — one niche's failure must not stop the run
        result["insight"] = "error"
        result["insight_reason"] = str(e)
        log.warning("niche insight synthesis failed for %s/%s: %s", platform, niche, e)

    try:
        trend_text = await generate_trend_insight(seeds, platform, niche)
        recent_count, established_count = count_recent_established(seeds)
        await _upsert(db, TrendSummary, platform, niche, {
            "trend_text": trend_text,
            "recent_seed_count": recent_count,
            "established_seed_count": established_count,
        })
        result["trend"] = "generated"
    except ValueError as e:
        result["trend"] = "skipped"
        result["trend_reason"] = str(e)
    except Exception as e:  # noqa: BLE001
        result["trend"] = "error"
        result["trend_reason"] = str(e)
        log.warning("trend insight synthesis failed for %s/%s: %s", platform, niche, e)

    return result


async def run_weekly_niche_synthesis() -> dict:
    """Entry point for the scheduler. Never raises — a failure here must not take
    down the process; the caller logs the summary."""
    if not niche_synthesis_enabled():
        return {"status": "disabled"}
    if not claude_configured():
        log.warning("niche synthesis skipped: ANTHROPIC_API_KEY not configured")
        return {"status": "skipped", "reason": "anthropic_not_configured"}

    results = []
    try:
        async with AsyncSessionLocal() as db:
            for platform in _PLATFORMS:
                seeds = (await db.execute(
                    select(SeedVideo).where(SeedVideo.platform == platform)
                )).scalars().all()
                by_niche: dict[str, list] = defaultdict(list)
                for s in seeds:
                    if s.rating is not None:
                        by_niche[s.niche].append(s)
                for niche, niche_seeds in by_niche.items():
                    results.append(await _synthesize_one(db, platform, niche, niche_seeds))
    except Exception as exc:  # noqa: BLE001 — scheduler job must degrade, not crash
        log.error("niche synthesis run crashed: %s: %s", type(exc).__name__, exc)
        return {"status": "error", "reason": str(exc), "results": results}

    generated = sum(1 for r in results if r.get("insight") == "generated" or r.get("trend") == "generated")
    return {"status": "ok", "niches_touched": len(results), "generated": generated, "results": results}


async def load_niche_synthesis_block(platform: str, niche: str) -> str:
    """Best-effort fetch of the stored weekly niche+trend synthesis text. Called
    from services.gemini.analyze_video and threaded into
    services.claude_scoring.score_from_perception's niche_synthesis_block
    parameter, the same pattern the (dormant) services.calibration.load_calibration_note
    uses for the DB-lookup-that-degrades-to-nothing shape.

    Gated by NICHE_SYNTHESIS_ENABLED — returns "" when disabled, when the niche is
    unresolved, when nothing has been generated yet, or on any failure. Never
    raises: this is optional enrichment, so any problem here means "grade
    un-nudged," exactly like a missing calibration note.
    """
    if not niche_synthesis_enabled():
        return ""
    if not niche or niche == "Uncategorized":
        return ""
    try:
        async with AsyncSessionLocal() as db:
            insight = (await db.execute(
                select(NicheInsight).where(NicheInsight.platform == platform, NicheInsight.niche == niche)
            )).scalar_one_or_none()
            trend = (await db.execute(
                select(TrendSummary).where(TrendSummary.platform == platform, TrendSummary.niche == niche)
            )).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 — optional enrichment, never fails grading
        log.warning("load_niche_synthesis_block %s/%s failed: %s", platform, niche, exc)
        return ""

    parts = []
    if insight is not None:
        parts.append(
            f"NICHE PATTERN SIGNAL (all-time, {insight.seed_count} seeds, "
            f"generated {insight.generated_at}):\n{insight.insight}"
        )
    if trend is not None:
        parts.append(
            f"RECENT TREND SIGNAL (last {RECENT_WINDOW_DAYS}d vs established, "
            f"generated {trend.generated_at}):\n{trend.trend_text}"
        )
    return "\n\n".join(parts)
