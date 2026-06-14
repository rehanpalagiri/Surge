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

_last_instagram_harvest: dict = {}


def _hashtag(keyword: str) -> str:
    """Convert a keyword phrase to a hashtag (no spaces, lowercase)."""
    return keyword.replace(" ", "").lower()


async def _search_hashtag(hashtag: str, amount: int = 20) -> list[dict]:
    """Fetch top Instagram Reels for a hashtag via HikerAPI."""
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
    keywords = NICHE_KEYWORDS.get(niche, [niche])
    added = skipped = errors = 0

    for keyword in keywords:
        if added >= max_videos:
            break
        hashtag = _hashtag(keyword)
        try:
            medias = await _search_hashtag(hashtag)
            await asyncio.sleep(1.5)  # HikerAPI rate-limit buffer
        except Exception as e:
            logger.warning("HikerAPI search failed '#%s': %s", hashtag, e)
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

            tmp = tempfile.mktemp(suffix=".mp4")
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

    return {"niche": niche, "added": added, "skipped": skipped, "errors": errors}


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
        "Instagram harvest started: %d niches min_likes=%d max_per_niche=%d",
        len(target), min_likes, max_per_niche,
    )
    try:
        results = []
        for niche in target:
            r = await harvest_instagram_niche(niche, min_likes, max_per_niche)
            results.append(r)

        total_added = sum(r["added"] for r in results)
        total_skipped = sum(r["skipped"] for r in results)
        total_errors = sum(r["errors"] for r in results)

        _last_instagram_harvest = {
            "status": "done",
            "platform": "instagram",
            "finished_at": datetime.utcnow().isoformat(),
            "niches_processed": len(results),
            "total_added": total_added,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
            "detail": results,
        }
        logger.info(
            "Instagram harvest done: added=%d skipped=%d errors=%d",
            total_added, total_skipped, total_errors,
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
