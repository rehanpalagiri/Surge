"""Instagram seed harvesting via HikerAPI (api.hikerapi.com).

Searches Instagram by hashtag per niche, filters for Reels with enough likes,
downloads the video, runs it through the same analyze_seed_video pipeline, and
persists with source="harvest". Likes replace views as the primary engagement
signal since Instagram hides view counts.

Entry points:
  harvest_instagram_all(niches, min_likes, max_per_niche)
  harvest_instagram_niche(niche, min_likes, max_videos)
  get_last_instagram_harvest()
"""
import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime
from services.clock import utc_now_naive
from typing import Optional

import httpx
from sqlalchemy import select

from database import AsyncSessionLocal
from models import SeedVideo
from services.seed_analysis import analyze_seed_video
from services.seed_harvest import NICHE_KEYWORDS

logger = logging.getLogger("instagram_harvest")

_HIKERAPI_BASE = "https://api.hikerapi.com"

DEFAULT_MIN_LIKES = 1_000
DEFAULT_MAX_PER_NICHE = 3
_IG_KEYWORDS_PER_NICHE = 2   # 50 niches × 2 = 100 calls = fits free tier exactly
_IG_RESULTS_PER_CALL = 50    # max candidates per hashtag search
_IG_CONCURRENCY = 3          # niches processed in parallel
_CIRCUIT_BREAKER_THRESHOLD = 3  # stop niche after this many consecutive Gemini failures

_last_instagram_harvest: dict = {}


def _hashtag(keyword: str) -> str:
    """Convert a keyword phrase to a hashtag (no spaces, lowercase)."""
    return keyword.replace(" ", "").lower()


def _get_hikerapi_key() -> str:
    """Read HIKERAPI_KEY at call time (not module load) so Railway env vars are always current."""
    return os.getenv("HIKERAPI_KEY", "")


async def _search_hashtag(hashtag: str, amount: int = _IG_RESULTS_PER_CALL) -> list[dict]:
    """Fetch top Instagram Reels for a hashtag via HikerAPI.
    Returns up to `amount` media objects in a single API call.
    """
    key = _get_hikerapi_key()
    if not key:
        raise ValueError("HIKERAPI_KEY is not set.")
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(
            f"{_HIKERAPI_BASE}/v1/hashtag/medias/top",
            params={"name": hashtag, "amount": amount},
            headers={"x-access-key": key, "accept": "application/json"},
        )
        r.raise_for_status()
        body = r.json()

    # Response is either a list directly or wrapped in {"items": [...]}
    if isinstance(body, list):
        items = body
    else:
        items = body.get("items") or body.get("medias") or []
    logger.info("HikerAPI '#%s' → %d candidates", hashtag, len(items))
    return items


async def _already_harvested(media_pk: str) -> bool:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SeedVideo.id).where(SeedVideo.notes.contains(f"ig:{media_pk}"))
        )
        return result.scalar() is not None


async def _download(url: str, dest: str) -> None:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
        async with http.stream("GET", url, headers={"User-Agent": "Mozilla/5.0"}) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in r.aiter_bytes(65536):
                    f.write(chunk)


async def harvest_instagram_niche(
    niche: str,
    min_likes: int = DEFAULT_MIN_LIKES,
    max_videos: int = DEFAULT_MAX_PER_NICHE,
) -> dict:
    # Use only the first N keywords to stay within HikerAPI free-tier budget.
    keywords = NICHE_KEYWORDS.get(niche, [niche])[:_IG_KEYWORDS_PER_NICHE]
    added = skipped = errors = search_failures = gemini_calls = 0
    # Granular skip counters.
    skip_not_reel = skip_missing_id = skip_missing_url = skip_below_min_likes = skip_duplicate = 0
    # Split error counters.
    download_errors = analysis_errors = db_errors = 0
    last_download_error = last_analysis_error = last_db_error = ""
    consecutive_errors = 0  # circuit breaker counter — resets on any success

    for keyword in keywords:
        if added >= max_videos:
            break
        if consecutive_errors >= _CIRCUIT_BREAKER_THRESHOLD:
            logger.warning(
                "Circuit breaker: stopping niche=%s after %d consecutive errors",
                niche, consecutive_errors,
            )
            break
        hashtag = _hashtag(keyword)
        try:
            medias = await _search_hashtag(hashtag)
            await asyncio.sleep(1.5)  # HikerAPI rate-limit buffer
        except Exception as e:
            logger.warning("HikerAPI search failed '#%s': %s", hashtag, e)
            search_failures += 1
            continue

        for media in medias:
            if added >= max_videos:
                break

            if consecutive_errors >= _CIRCUIT_BREAKER_THRESHOLD:
                logger.warning(
                    "Circuit breaker: stopping niche=%s after %d consecutive errors",
                    niche, consecutive_errors,
                )
                break

            # Only process Reels (media_type=2, product_type="clips")
            media_type = media.get("media_type")
            product_type = media.get("product_type", "")
            if media_type != 2 or product_type != "clips":
                skip_not_reel += 1
                skipped += 1
                continue

            media_pk = str(media.get("pk") or media.get("id") or "")
            like_count = int(media.get("like_count") or 0)
            video_url = media.get("video_url") or ""

            if not media_pk:
                skip_missing_id += 1
                skipped += 1
                continue
            if not video_url:
                skip_missing_url += 1
                skipped += 1
                continue
            if like_count < min_likes:
                skip_below_min_likes += 1
                skipped += 1
                continue

            if await _already_harvested(media_pk):
                skip_duplicate += 1
                skipped += 1
                continue

            fd, tmp = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            try:
                # Step 1: Download — tracked separately from analysis failures.
                try:
                    await _download(video_url, tmp)
                except Exception as e:
                    msg = str(e)[:200]
                    logger.error("Download error niche=%s ig=%s: %s", niche, media_pk, e)
                    download_errors += 1
                    errors += 1
                    consecutive_errors += 1
                    last_download_error = msg
                    continue

                # Step 2: Gemini analysis — tracked separately.
                gemini_calls += 1
                result = await analyze_seed_video(tmp, "instagram", niche, None, like_count)

                if "error" in result or "seed_quality" not in result:
                    err_msg = str(result.get("error", "missing seed_quality"))[:200]
                    logger.warning("Analysis failed ig:%s — %s", media_pk, err_msg)
                    analysis_errors += 1
                    errors += 1
                    consecutive_errors += 1
                    last_analysis_error = err_msg
                    continue

                consecutive_errors = 0  # success — reset the circuit breaker
                rating = max(0, min(10, int(round(float(result["seed_quality"])))))
                caption = str(media.get("caption_text") or "").strip()[:300]
                note_parts = [f"Auto-harvested Instagram · hashtag: #{hashtag} · ig:{media_pk}"]
                if caption:
                    note_parts.append(caption)

                # Step 3: DB insert — tracked separately.
                try:
                    async with AsyncSessionLocal() as db:
                        seed = SeedVideo(
                            filename=f"ig-harvest-{media_pk}.mp4",
                            platform="instagram",
                            niche=niche,
                            view_count=None,
                            like_count=like_count,
                            rating=rating,
                            gemini_analysis=json.dumps(result),
                            notes=" · ".join(note_parts),
                            source="harvest",
                        )
                        db.add(seed)
                        await db.commit()
                except Exception as e:
                    msg = str(e)[:200]
                    logger.error("DB error niche=%s ig=%s: %s", niche, media_pk, e)
                    db_errors += 1
                    errors += 1
                    consecutive_errors += 1
                    last_db_error = msg
                    continue

                added += 1
                logger.info(
                    "Harvested Instagram niche=%s ig=%s rating=%d likes=%d",
                    niche, media_pk, rating, like_count,
                )

            except Exception as e:
                logger.error("Instagram harvest error niche=%s ig=%s: %s", niche, media_pk, e)
                errors += 1
                consecutive_errors += 1
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)

    logger.info(
        "harvest_instagram_niche done niche=%s added=%d skipped=%d(not_reel=%d below_likes=%d dup=%d) "
        "search_fail=%d gemini=%d dl_err=%d analysis_err=%d db_err=%d",
        niche, added, skipped, skip_not_reel, skip_below_min_likes, skip_duplicate,
        search_failures, gemini_calls, download_errors, analysis_errors, db_errors,
    )
    return {
        "niche": niche,
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "search_failures": search_failures,
        "gemini_calls": gemini_calls,
        "skip_not_reel": skip_not_reel,
        "skip_missing_id": skip_missing_id,
        "skip_missing_url": skip_missing_url,
        "skip_below_min_likes": skip_below_min_likes,
        "skip_duplicate": skip_duplicate,
        "download_errors": download_errors,
        "analysis_errors": analysis_errors,
        "db_errors": db_errors,
        "last_download_error": last_download_error,
        "last_analysis_error": last_analysis_error,
        "last_db_error": last_db_error,
    }


async def harvest_instagram_all(
    niches: Optional[list[str]] = None,
    min_likes: int = DEFAULT_MIN_LIKES,
    max_per_niche: int = DEFAULT_MAX_PER_NICHE,
) -> None:
    global _last_instagram_harvest
    target = niches or list(NICHE_KEYWORDS.keys())
    _last_instagram_harvest = {
        "status": "running",
        "started_at": utc_now_naive().isoformat(),
        "platform": "instagram",
    }

    # Early exit: HIKERAPI_KEY missing means 100% search failure rate.
    if not _get_hikerapi_key():
        logger.error("Instagram harvest aborted: HIKERAPI_KEY is not set")
        _last_instagram_harvest = {
            "status": "failed",
            "platform": "instagram",
            "finished_at": utc_now_naive().isoformat(),
            "error": "HIKERAPI_KEY is not set. Add it to your environment variables.",
        }
        return

    logger.info(
        "Instagram harvest started: %d niches min_likes=%d max_per_niche=%d concurrency=%d",
        len(target), min_likes, max_per_niche, _IG_CONCURRENCY,
    )
    try:
        sem = asyncio.Semaphore(_IG_CONCURRENCY)
        _running: dict = {
            "added": 0, "skipped": 0, "errors": 0, "gemini_calls": 0,
            "search_failures": 0, "niches_done": 0,
            "skip_not_reel": 0, "skip_missing_id": 0, "skip_missing_url": 0,
            "skip_below_min_likes": 0, "skip_duplicate": 0,
            "download_errors": 0, "analysis_errors": 0, "db_errors": 0,
            "last_download_error": "", "last_analysis_error": "", "last_db_error": "",
        }

        async def _run(niche: str) -> dict:
            async with sem:
                result = await harvest_instagram_niche(niche, min_likes, max_per_niche)
            _running["added"] += result["added"]
            _running["skipped"] += result["skipped"]
            _running["errors"] += result["errors"]
            _running["gemini_calls"] += result.get("gemini_calls", 0)
            _running["search_failures"] += result.get("search_failures", 0)
            _running["skip_not_reel"] += result.get("skip_not_reel", 0)
            _running["skip_missing_id"] += result.get("skip_missing_id", 0)
            _running["skip_missing_url"] += result.get("skip_missing_url", 0)
            _running["skip_below_min_likes"] += result.get("skip_below_min_likes", 0)
            _running["skip_duplicate"] += result.get("skip_duplicate", 0)
            _running["download_errors"] += result.get("download_errors", 0)
            _running["analysis_errors"] += result.get("analysis_errors", 0)
            _running["db_errors"] += result.get("db_errors", 0)
            if result.get("last_download_error"):
                _running["last_download_error"] = result["last_download_error"]
            if result.get("last_analysis_error"):
                _running["last_analysis_error"] = result["last_analysis_error"]
            if result.get("last_db_error"):
                _running["last_db_error"] = result["last_db_error"]
            _running["niches_done"] += 1
            _last_instagram_harvest.update({
                "niches_processed": _running["niches_done"],
                "total_added": _running["added"],
                "total_skipped": _running["skipped"],
                "total_errors": _running["errors"],
                "total_gemini_calls": _running["gemini_calls"],
                "total_search_failures": _running["search_failures"],
                "total_skip_not_reel": _running["skip_not_reel"],
                "total_skip_missing_id": _running["skip_missing_id"],
                "total_skip_missing_url": _running["skip_missing_url"],
                "total_skip_below_min_likes": _running["skip_below_min_likes"],
                "total_skip_duplicate": _running["skip_duplicate"],
                "total_download_errors": _running["download_errors"],
                "total_analysis_errors": _running["analysis_errors"],
                "total_db_errors": _running["db_errors"],
                "last_download_error": _running["last_download_error"],
                "last_analysis_error": _running["last_analysis_error"],
                "last_db_error": _running["last_db_error"],
            })
            return result

        raw = await asyncio.gather(*[_run(n) for n in target], return_exceptions=True)
        results = [r for r in raw if isinstance(r, dict)]
        failed_niches = 0
        for r in raw:
            if isinstance(r, Exception):
                failed_niches += 1
                logger.error("Instagram niche task crashed: %s", r)

        total_added = _running["added"]
        total_errors = _running["errors"]
        total_search_failures = _running["search_failures"]

        if total_added == 0 and (total_errors > 0 or total_search_failures > 0):
            final_status = "degraded"
        else:
            final_status = "done"

        _last_instagram_harvest = {
            "status": final_status,
            "platform": "instagram",
            "finished_at": utc_now_naive().isoformat(),
            "niches_processed": len(results),
            "total_added": total_added,
            "total_skipped": _running["skipped"],
            "total_errors": total_errors,
            "total_gemini_calls": _running["gemini_calls"],
            "total_search_failures": total_search_failures,
            "total_skip_not_reel": _running["skip_not_reel"],
            "total_skip_missing_id": _running["skip_missing_id"],
            "total_skip_missing_url": _running["skip_missing_url"],
            "total_skip_below_min_likes": _running["skip_below_min_likes"],
            "total_skip_duplicate": _running["skip_duplicate"],
            "total_download_errors": _running["download_errors"],
            "total_analysis_errors": _running["analysis_errors"],
            "total_db_errors": _running["db_errors"],
            "last_download_error": _running["last_download_error"],
            "last_analysis_error": _running["last_analysis_error"],
            "last_db_error": _running["last_db_error"],
            "failed_niches": failed_niches,
            "detail": results,
        }
        logger.info(
            "Instagram harvest done: status=%s added=%d skipped=%d errors=%d(dl=%d analysis=%d db=%d) "
            "gemini=%d search_fail=%d failed_niches=%d",
            final_status, total_added, _running["skipped"], total_errors,
            _running["download_errors"], _running["analysis_errors"], _running["db_errors"],
            _running["gemini_calls"], total_search_failures, failed_niches,
        )
    except Exception as e:
        logger.error("Instagram harvest failed: %s", e)
        _last_instagram_harvest = {
            "status": "failed",
            "platform": "instagram",
            "finished_at": utc_now_naive().isoformat(),
            "error": str(e),
        }


def get_last_instagram_harvest() -> dict:
    return _last_instagram_harvest
