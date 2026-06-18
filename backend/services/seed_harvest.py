"""
Door A: automated seed harvesting via tikwm keyword search.

Searches TikTok for top-performing videos per niche, filters by minimum view
count, deduplicates against existing seeds, downloads the video, runs it through
the same analyze_seed_video pipeline admins use, and persists with source="harvest".

Entry points:
  harvest_all(niches, min_views, max_per_niche)  — called by BackgroundTasks
  harvest_niche(niche, min_views, max_videos)    — single-niche variant
  get_last_harvest()                             — in-memory last-run summary
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

logger = logging.getLogger("seed_harvest")

# ── Niche → keywords ─────────────────────────────────────────────────────────
# 3-4 TikTok-style search terms per canonical niche.
# Keys MUST match CANONICAL_NICHES exactly (used for seed bucketing).

NICHE_KEYWORDS: dict[str, list[str]] = {
    "Fitness & Gym":               ["gym workout", "fitness motivation", "strength training", "gym transformation"],
    "Comedy & Skits":              ["funny skit", "comedy tiktok", "relatable humor", "prank video"],
    "Food & Cooking":              ["easy recipe", "cooking hack", "what I eat in a day", "meal prep"],
    "Fashion & Style":             ["outfit of the day", "fashion haul", "style tips", "ootd tiktok"],
    "Beauty & Makeup":             ["makeup tutorial", "glam makeup", "makeup transformation", "drugstore makeup"],
    "Education & Tutorials":       ["learn something new", "life hack", "did you know", "tutorial tiktok"],
    "Gaming":                      ["gaming highlights", "gaming setup", "game clips", "esports tiktok"],
    "Music & Dance":               ["dance challenge", "dance tutorial", "singing cover", "original song"],
    "Tech & Gadgets":              ["tech review", "new gadgets", "iphone tips", "tech unboxing"],
    "Finance & Investing":         ["money tips", "investing for beginners", "personal finance", "budgeting tips"],
    "Health & Wellness":           ["wellness routine", "healthy lifestyle", "mental wellness", "self care"],
    "Travel & Adventure":          ["travel vlog", "travel tips", "hidden gems", "solo travel"],
    "Lifestyle & Vlogs":           ["day in my life", "morning routine", "lifestyle vlog", "weekly vlog"],
    "Motivation & Mindset":        ["motivation speech", "mindset tips", "self improvement", "daily habits"],
    "Sports & Athletics":          ["sports highlights", "athlete training", "extreme sports", "basketball tiktok"],
    "Relationships & Dating":      ["relationship advice", "dating tips", "couples goals", "love advice"],
    "Art & Creativity":            ["art process", "drawing tutorial", "digital art", "art timelapse"],
    "Business & Entrepreneurship": ["entrepreneur tips", "small business", "startup advice", "business hack"],
    "Pets & Animals":              ["dog training", "cute cat", "funny pets", "pet care tips"],
    "Parenting & Family":          ["mom life", "parenting tips", "baby milestone", "family vlog"],
    "Skincare & Glow":             ["skincare routine", "glass skin", "acne tips", "skincare beginner"],
    "Weight Loss Journey":         ["weight loss journey", "fat loss tips", "body transformation", "calorie deficit"],
    "Yoga & Meditation":           ["yoga flow", "morning yoga", "meditation guide", "yoga for beginners"],
    "Baking & Desserts":           ["baking tutorial", "cake decorating", "dessert recipe", "cookie recipe"],
    "Vegan & Plant-Based":         ["vegan recipe", "plant based meal", "vegan lifestyle", "vegan cooking"],
    "DIY & Crafts":                ["diy project", "craft ideas", "handmade tiktok", "thrift flip"],
    "Home Decor & Interior":       ["home decor ideas", "room makeover", "apartment tour", "interior design"],
    "Cleaning & Organization":     ["cleaning motivation", "clean with me", "declutter tips", "organization hack"],
    "Career & Job Tips":           ["job interview tips", "career advice", "resume tips", "work tips"],
    "Real Estate":                 ["real estate tips", "house tour", "property investment", "first home buyer"],
    "Side Hustles":                ["side hustle ideas", "make money online", "passive income", "work from home"],
    "Crypto & Web3":               ["crypto tips", "bitcoin explained", "web3 beginners", "crypto trading"],
    "Outdoor & Hiking":            ["hiking adventure", "camping tips", "nature walk", "trail running"],
    "True Crime & Mystery":        ["true crime story", "unsolved mystery", "crime documentary", "cold case"],
    "Books & Reading":             ["book recommendations", "booktok", "reading vlog", "book review"],
    "Astrology & Spirituality":    ["astrology reading", "tarot reading", "manifestation tips", "law of attraction"],
    "Movies & TV":                 ["movie recommendation", "netflix review", "tv show reaction", "movie analysis"],
    "Cars & Automotive":           ["car review", "car modification", "car tips", "dream car tiktok"],
    "Photography & Editing":       ["photography tips", "photo editing tutorial", "camera settings", "lightroom tips"],
    "Sustainability & Eco":        ["sustainable living", "zero waste tips", "eco friendly", "thrift shopping"],
    "Mental Health":               ["mental health tips", "anxiety advice", "therapy talk", "emotional healing"],
    "Cooking on a Budget":         ["cheap meal ideas", "budget cooking", "frugal meals", "budget recipe"],
    "Couples & Romance":           ["couple goals", "relationship milestones", "date night ideas", "couples tiktok"],
    "College & Student Life":      ["college tips", "student life", "dorm room tour", "study hack"],
    "Luxury & Wealth":             ["luxury lifestyle", "rich life", "luxury travel", "expensive tiktok"],
    "Street Style & Thrift":       ["thrift haul", "street fashion", "vintage finds", "thrift flip outfit"],
    "Hair Care & Styling":         ["hair tutorial", "hair transformation", "natural hair care", "hairstyle ideas"],
    "Kids & Baby":                 ["baby milestone", "toddler activities", "newborn tips", "kids tiktok"],
    "ASMR & Relaxation":           ["asmr tiktok", "relaxing video", "satisfying sounds", "sleep sounds"],
    "News & Commentary":           ["news explained", "political commentary", "current events", "opinion tiktok"],
}

DEFAULT_MIN_VIEWS = 500_000
DEFAULT_MAX_PER_NICHE = 3
_TIKTOK_CONCURRENCY = 3  # niches processed in parallel (matches Instagram harvester)

# Stop retrying within a niche after this many consecutive Gemini failures.
# Prevents hammering quota when the API is rate-limited or the key is exhausted.
_CIRCUIT_BREAKER_THRESHOLD = 3

# Single-instance in-memory state (Railway = one process)
_last_harvest: dict = {}


async def _search_tiktok(keyword: str, count: int = 20) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(
            "https://www.tikwm.com/api/feed/search",
            params={"keywords": keyword, "count": count},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()
        body = r.json()
    if body.get("code") != 0:
        raise ValueError(f"tikwm search '{keyword}': {body.get('msg')}")
    return body.get("data", {}).get("videos", [])


async def _already_harvested(video_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SeedVideo.id).where(SeedVideo.notes.contains(f"vid:{video_id}"))
        )
        return result.scalar() is not None


async def _download(url: str, dest: str) -> None:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
        async with http.stream("GET", url, headers={"User-Agent": "Mozilla/5.0"}) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in r.aiter_bytes(65536):
                    f.write(chunk)


async def harvest_niche(
    niche: str,
    min_views: int = DEFAULT_MIN_VIEWS,
    max_videos: int = DEFAULT_MAX_PER_NICHE,
) -> dict:
    keywords = NICHE_KEYWORDS.get(niche, [niche])
    added = skipped = errors = search_failures = gemini_calls = 0
    consecutive_errors = 0  # circuit breaker counter — resets on any success

    for keyword in keywords:
        if added >= max_videos:
            break
        if consecutive_errors >= _CIRCUIT_BREAKER_THRESHOLD:
            logger.warning(
                "Circuit breaker: skipping remaining keywords for niche=%s after %d consecutive errors",
                niche, consecutive_errors,
            )
            break
        try:
            videos = await _search_tiktok(keyword)
            await asyncio.sleep(1.2)  # tikwm free tier ~1 req/sec
        except Exception as e:
            logger.warning("Search failed '%s': %s", keyword, e)
            search_failures += 1
            continue

        for v in videos:
            if added >= max_videos:
                break

            # Circuit breaker: stop this niche if Gemini is consistently failing.
            # Prevents draining daily quota when rate-limited or key is exhausted.
            if consecutive_errors >= _CIRCUIT_BREAKER_THRESHOLD:
                logger.warning(
                    "Circuit breaker: stopping niche=%s after %d consecutive Gemini errors",
                    niche, consecutive_errors,
                )
                break

            video_id = str(v.get("video_id", ""))
            play_count = int(v.get("play_count") or 0)
            like_count = int(v.get("digg_count") or 0)
            play_url = v.get("play", "")

            if not video_id or not play_url or play_count < min_views:
                skipped += 1
                continue

            if await _already_harvested(video_id):
                skipped += 1
                continue

            fd, tmp = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)  # _download reopens by path; we don't need the fd
            try:
                await _download(play_url, tmp)
                gemini_calls += 1
                result = await analyze_seed_video(tmp, "tiktok", niche, play_count, like_count)

                if "error" in result or "virality_rating" not in result:
                    logger.warning("Analysis failed vid:%s — %s", video_id, result.get("error"))
                    errors += 1
                    consecutive_errors += 1
                    continue

                consecutive_errors = 0  # success — reset the circuit breaker
                rating = max(0, min(10, int(round(float(result["virality_rating"])))))
                caption = str(v.get("title") or "").strip()[:300]
                note_parts = [f"Auto-harvested · keyword: {keyword!r} · vid:{video_id}"]
                if caption:
                    note_parts.append(caption)

                async with AsyncSessionLocal() as db:
                    seed = SeedVideo(
                        filename=f"harvest-{video_id}.mp4",
                        platform="tiktok",
                        niche=niche,
                        view_count=play_count,
                        like_count=like_count,
                        rating=rating,
                        gemini_analysis=json.dumps(result),
                        notes=" · ".join(note_parts),
                        source="harvest",
                    )
                    db.add(seed)
                    await db.commit()

                added += 1
                logger.info("Harvested niche=%s vid=%s rating=%d views=%d", niche, video_id, rating, play_count)

            except Exception as e:
                logger.error("Harvest error niche=%s vid=%s: %s", niche, video_id, e)
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


async def harvest_all(
    niches: Optional[list[str]] = None,
    min_views: int = DEFAULT_MIN_VIEWS,
    max_per_niche: int = DEFAULT_MAX_PER_NICHE,
) -> None:
    global _last_harvest
    target = niches or list(NICHE_KEYWORDS.keys())
    _last_harvest = {"status": "running", "started_at": datetime.utcnow().isoformat()}
    logger.info("Harvest started: %d niches min_views=%d max_per_niche=%d", len(target), min_views, max_per_niche)

    try:
        sem = asyncio.Semaphore(_TIKTOK_CONCURRENCY)
        # Live running totals — updated after each niche so polling shows progress.
        _running: dict = {"added": 0, "skipped": 0, "errors": 0, "gemini_calls": 0,
                          "search_failures": 0, "niches_done": 0, "failed_niches": 0}

        async def _run(niche: str) -> dict:
            async with sem:
                result = await harvest_niche(niche, min_views, max_per_niche)
            # Update live totals immediately after each niche finishes.
            _running["added"] += result["added"]
            _running["skipped"] += result["skipped"]
            _running["errors"] += result["errors"]
            _running["gemini_calls"] += result.get("gemini_calls", 0)
            _running["search_failures"] += result.get("search_failures", 0)
            _running["niches_done"] += 1
            _last_harvest.update({
                "niches_processed": _running["niches_done"],
                "total_added": _running["added"],
                "total_skipped": _running["skipped"],
                "total_errors": _running["errors"],
                "total_gemini_calls": _running["gemini_calls"],
                "total_search_failures": _running["search_failures"],
            })
            return result

        # return_exceptions=True: one niche crashing must not discard every other
        # niche's completed work.
        raw = await asyncio.gather(*[_run(n) for n in target], return_exceptions=True)
        results = [r for r in raw if isinstance(r, dict)]
        failed_niches = 0
        for r in raw:
            if isinstance(r, Exception):
                failed_niches += 1
                logger.error("TikTok niche task crashed: %s", r)

        total_added = _running["added"]
        total_skipped = _running["skipped"]
        total_errors = _running["errors"]
        total_gemini_calls = _running["gemini_calls"]
        total_search_failures = _running["search_failures"]

        _last_harvest = {
            "status": "done",
            "finished_at": datetime.utcnow().isoformat(),
            "niches_processed": len(results),
            "total_added": total_added,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
            "total_gemini_calls": total_gemini_calls,
            "total_search_failures": total_search_failures,
            "failed_niches": failed_niches,
            "detail": results,
        }
        logger.info(
            "Harvest done: added=%d skipped=%d errors=%d gemini_calls=%d search_failures=%d failed_niches=%d",
            total_added, total_skipped, total_errors, total_gemini_calls, total_search_failures, failed_niches,
        )
    except Exception as e:
        logger.error("Harvest failed: %s", e)
        _last_harvest = {
            "status": "failed",
            "finished_at": datetime.utcnow().isoformat(),
            "error": str(e),
        }


def get_last_harvest() -> dict:
    return _last_harvest
