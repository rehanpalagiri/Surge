"""
Trending Feed harvest — pulls RECENTLY high-performing TikTok videos per niche.

Unlike the regular keyword harvest (which finds any high-performing video regardless of age),
this specifically targets videos posted in the last 30 days that are already
accumulating high view counts. A video with 500K views in 7 days vs 500K in 6 months
is a completely different signal — view velocity is the trend detector.

Entry points:
  harvest_trending(niches, max_age_days, min_velocity, max_per_niche)
  get_last_trend_harvest()
"""
import asyncio
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from database import AsyncSessionLocal
from models import SeedVideo
from services.seed_analysis import analyze_seed_video
from services.seed_harvest import NICHE_KEYWORDS, _search_tiktok, _download, _already_harvested

logger = logging.getLogger("trend_harvest")

DEFAULT_TREND_MAX_AGE_DAYS = 30      # only videos published in the last 30 days
DEFAULT_TREND_MIN_VELOCITY = 20_000  # views/day minimum — filters slow accumulators
DEFAULT_TREND_MAX_PER_NICHE = 2
_TREND_CONCURRENCY = 3
_CIRCUIT_BREAKER_THRESHOLD = 3

_last_trend_harvest: dict = {}


async def harvest_trending_niche(
    niche: str,
    max_age_days: int = DEFAULT_TREND_MAX_AGE_DAYS,
    min_velocity: float = DEFAULT_TREND_MIN_VELOCITY,
    max_videos: int = DEFAULT_TREND_MAX_PER_NICHE,
) -> dict:
    keywords = NICHE_KEYWORDS.get(niche, [niche])
    added = skipped = errors = search_failures = gemini_calls = 0
    consecutive_errors = 0
    cutoff_ts = time.time() - (max_age_days * 86400)

    for keyword in keywords:
        if added >= max_videos:
            break
        if consecutive_errors >= _CIRCUIT_BREAKER_THRESHOLD:
            logger.warning(
                "Circuit breaker: skipping remaining keywords for trend niche=%s after %d consecutive errors",
                niche, consecutive_errors,
            )
            break
        try:
            # Fetch more candidates since most will be filtered by recency
            videos = await _search_tiktok(keyword, count=30)
            await asyncio.sleep(1.2)
        except Exception as e:
            logger.warning("Trend search failed '%s': %s", keyword, e)
            search_failures += 1
            continue

        for v in videos:
            if added >= max_videos:
                break
            if consecutive_errors >= _CIRCUIT_BREAKER_THRESHOLD:
                logger.warning(
                    "Circuit breaker: trend niche=%s after %d consecutive Gemini errors",
                    niche, consecutive_errors,
                )
                break

            video_id = str(v.get("video_id", ""))
            play_count = int(v.get("play_count") or 0)
            like_count = int(v.get("digg_count") or 0)
            play_url = v.get("play", "")
            create_time = int(v.get("create_time") or 0)

            if not video_id or not play_url:
                skipped += 1
                continue

            # Must be recently published
            if create_time == 0 or create_time < cutoff_ts:
                skipped += 1
                continue

            # Viral velocity = views per day since posting
            days_alive = max(0.5, (time.time() - create_time) / 86400)
            velocity = play_count / days_alive

            if velocity < min_velocity:
                skipped += 1
                continue

            if await _already_harvested(video_id):
                skipped += 1
                continue

            fd, tmp = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            try:
                await _download(play_url, tmp)
                gemini_calls += 1
                result = await analyze_seed_video(tmp, "tiktok", niche, play_count, like_count)

                if "error" in result or "seed_quality" not in result:
                    logger.warning("Trend analysis failed vid:%s — %s", video_id, result.get("error"))
                    errors += 1
                    consecutive_errors += 1
                    continue

                consecutive_errors = 0
                rating = max(0, min(10, int(round(float(result["seed_quality"])))))
                posted_at_dt = datetime.utcfromtimestamp(create_time) if create_time else None
                caption = str(v.get("title") or "").strip()[:300]
                note_parts = [
                    f"Trending harvest · keyword: {keyword!r} · vid:{video_id} "
                    f"· velocity:{velocity:.0f}/day"
                ]
                if caption:
                    note_parts.append(caption)

                async with AsyncSessionLocal() as db:
                    seed = SeedVideo(
                        filename=f"trend-{video_id}.mp4",
                        platform="tiktok",
                        niche=niche,
                        view_count=play_count,
                        like_count=like_count,
                        rating=rating,
                        gemini_analysis=json.dumps(result),
                        notes=" · ".join(note_parts),
                        source="trending",
                        posted_at=posted_at_dt,
                    )
                    db.add(seed)
                    await db.commit()

                added += 1
                logger.info(
                    "Trend seed: niche=%s vid=%s rating=%d views=%d velocity=%.0f/day",
                    niche, video_id, rating, play_count, velocity,
                )

            except Exception as e:
                logger.error("Trend harvest error niche=%s vid=%s: %s", niche, video_id, e)
                errors += 1
                consecutive_errors += 1
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)

    return {
        "niche": niche,
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "search_failures": search_failures,
        "gemini_calls": gemini_calls,
    }


async def harvest_trending(
    niches: Optional[list[str]] = None,
    max_age_days: int = DEFAULT_TREND_MAX_AGE_DAYS,
    min_velocity: float = DEFAULT_TREND_MIN_VELOCITY,
    max_per_niche: int = DEFAULT_TREND_MAX_PER_NICHE,
) -> None:
    global _last_trend_harvest
    target = niches or list(NICHE_KEYWORDS.keys())
    _last_trend_harvest = {"status": "running", "started_at": datetime.utcnow().isoformat()}
    logger.info("Trend harvest started: %d niches min_velocity=%.0f/day", len(target), min_velocity)

    try:
        sem = asyncio.Semaphore(_TREND_CONCURRENCY)
        _running: dict = {"added": 0, "skipped": 0, "errors": 0, "gemini_calls": 0,
                          "search_failures": 0, "niches_done": 0}

        async def _run(niche: str) -> dict:
            async with sem:
                result = await harvest_trending_niche(niche, max_age_days, min_velocity, max_per_niche)
            _running["added"] += result["added"]
            _running["skipped"] += result["skipped"]
            _running["errors"] += result["errors"]
            _running["gemini_calls"] += result.get("gemini_calls", 0)
            _running["search_failures"] += result.get("search_failures", 0)
            _running["niches_done"] += 1
            _last_trend_harvest.update({
                "niches_processed": _running["niches_done"],
                "total_added": _running["added"],
                "total_skipped": _running["skipped"],
                "total_errors": _running["errors"],
                "total_gemini_calls": _running["gemini_calls"],
                "total_search_failures": _running["search_failures"],
            })
            return result

        raw = await asyncio.gather(*[_run(n) for n in target], return_exceptions=True)
        results = [r for r in raw if isinstance(r, dict)]
        failed_niches = sum(1 for r in raw if isinstance(r, Exception))

        _last_trend_harvest = {
            "status": "done",
            "finished_at": datetime.utcnow().isoformat(),
            "niches_processed": len(results),
            "total_added": _running["added"],
            "total_skipped": _running["skipped"],
            "total_errors": _running["errors"],
            "total_gemini_calls": _running["gemini_calls"],
            "total_search_failures": _running["search_failures"],
            "failed_niches": failed_niches,
        }
        logger.info(
            "Trend harvest done: added=%d skipped=%d errors=%d gemini_calls=%d",
            _running["added"], _running["skipped"], _running["errors"], _running["gemini_calls"],
        )
    except Exception as e:
        logger.error("Trend harvest failed: %s", e)
        _last_trend_harvest = {
            "status": "failed",
            "finished_at": datetime.utcnow().isoformat(),
            "error": str(e),
        }


def get_last_trend_harvest() -> dict:
    return _last_trend_harvest
