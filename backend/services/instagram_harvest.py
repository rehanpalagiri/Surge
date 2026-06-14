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
from typing import Optional

import httpx
from sqlalchemy import select

from database import AsyncSessionLocal
from models import SeedVideo
from services.seed_analysis import analyze_seed_video
from services.seed_harvest import NICHE_KEYWORDS

logger = logging.getLogger("instagram_harvest")

_HIKERAPI_BASE = "https://api.hikerapi.com"
_HIKERAPI_KEY = os.getenv("HIKERAPI_KEY", "")

DEFAULT_MIN_LIKES = 1_000
DEFAULT_MAX_PER_NICHE = 3
_IG_KEYWORDS_PER_NICHE = 2   # 50 niches × 2 = 100 calls = fits free tier exactly
_IG_RESULTS_PER_CALL = 50    # max candidates per hashtag search
_IG_CONCURRENCY = 3          # niches processed in parallel

_last_instagram_harvest: dict = {}


def _hashtag(keyword: str) -> str:
    """Convert a keyword phrase to a hashtag (no spaces, lowercase)."""
    return keyword.replace(" ", "").lower()


async def _search_hashtag(hashtag: str, amount: int = _IG_RESULTS_PER_CALL) -> list[dict]:
    """Fetch top Instagram Reels for a hashtag via HikerAPI.
    Returns up to `amount` media objects in a single API call.
    """
    if not _HIKERAPI_KEY:
        raise ValueError("HIKERAPI_KEY is not set.")
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(
            f"{_HIKERAPI_BASE}/v1/hashtag/medias/top",
            params={"name": hashtag, "amount": amount},
            headers={"x-access-key": _HIKERAPI_KEY, "accept": "application/json"},
        )
        r.raise_for_status()
        body = r.json()

    # Response is either a list directly or wrapped in {"items": [...]}
    if isinstance(body, list):
        return body
    return body.get("items") or body.get("medias") or []


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
    added = skipped = errors = search_failures = 0

    for keyword in keywords:
        if added >= max_videos:
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

            # Only process Reels (media_type=2, product_type="clips")
            media_type = media.get("media_type")
            product_type = media.get("product_type", "")
            if media_type != 2 or product_type != "clips":
                skipped += 1
                continue

            media_pk = str(media.get("pk") or media.get("id") or "")
            like_count = int(media.get("like_count") or 0)
            video_url = media.get("video_url") or ""

            if not media_pk or not video_url or like_count < min_likes:
                skipped += 1
                continue

            if await _already_harvested(media_pk):
                skipped += 1
                continue

            fd, tmp = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)  # _download reopens by path; we don't need the fd
            try:
                await _download(video_url, tmp)
                result = await analyze_seed_video(tmp, "instagram", niche, None, like_count)

                if "error" in result or "virality_rating" not in result:
                    logger.warning("Analysis failed ig:%s — %s", media_pk, result.get("error"))
                    errors += 1
                    continue

                rating = max(0, min(10, int(round(float(result["virality_rating"])))))
                caption = str(media.get("caption_text") or "").strip()[:300]
                note_parts = [f"Auto-harvested Instagram · hashtag: #{hashtag} · ig:{media_pk}"]
                if caption:
                    note_parts.append(caption)

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

                added += 1
                logger.info(
                    "Harvested Instagram niche=%s ig=%s rating=%d likes=%d",
                    niche, media_pk, rating, like_count,
                )

            except Exception as e:
                logger.error("Instagram harvest error niche=%s ig=%s: %s", niche, media_pk, e)
                errors += 1
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)

    return {
        "niche": niche,
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "search_failures": search_failures,
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
        "started_at": datetime.utcnow().isoformat(),
        "platform": "instagram",
    }
    logger.info(
        "Instagram harvest started: %d niches min_likes=%d max_per_niche=%d concurrency=%d",
        len(target), min_likes, max_per_niche, _IG_CONCURRENCY,
    )
    try:
        sem = asyncio.Semaphore(_IG_CONCURRENCY)

        async def _run(niche: str) -> dict:
            async with sem:
                return await harvest_instagram_niche(niche, min_likes, max_per_niche)

        # return_exceptions=True: one niche crashing must not discard every other
        # niche's completed work (this is a budgeted, paid API run).
        raw = await asyncio.gather(*[_run(n) for n in target], return_exceptions=True)
        results = [r for r in raw if isinstance(r, dict)]
        failed_niches = 0
        for r in raw:
            if isinstance(r, Exception):
                failed_niches += 1
                logger.error("Instagram niche task crashed: %s", r)

        total_added = sum(r["added"] for r in results)
        total_skipped = sum(r["skipped"] for r in results)
        total_errors = sum(r["errors"] for r in results)
        total_search_failures = sum(r.get("search_failures", 0) for r in results)

        _last_instagram_harvest = {
            "status": "done",
            "platform": "instagram",
            "finished_at": datetime.utcnow().isoformat(),
            "niches_processed": len(results),
            "total_added": total_added,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
            "total_search_failures": total_search_failures,
            "failed_niches": failed_niches,
            "detail": results,
        }
        logger.info(
            "Instagram harvest done: added=%d skipped=%d errors=%d search_failures=%d failed_niches=%d",
            total_added, total_skipped, total_errors, total_search_failures, failed_niches,
        )
    except Exception as e:
        logger.error("Instagram harvest failed: %s", e)
        _last_instagram_harvest = {
            "status": "failed",
            "platform": "instagram",
            "finished_at": datetime.utcnow().isoformat(),
            "error": str(e),
        }


def get_last_instagram_harvest() -> dict:
    return _last_instagram_harvest
