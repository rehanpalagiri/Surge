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
    "Fitness":        ["gym workout", "fitness motivation", "strength training", "gym transformation"],
    "Comedy":         ["funny skit", "comedy tiktok", "relatable humor", "prank video"],
    "Food":           ["easy recipe", "cooking hack", "what I eat in a day", "meal prep"],
    "Fashion":        ["outfit of the day", "fashion haul", "style tips", "ootd tiktok"],
    "Beauty":         ["makeup tutorial", "glam makeup", "makeup transformation", "drugstore makeup"],
    "Education":      ["learn something new", "life hack", "did you know", "tutorial tiktok"],
    "Gaming":         ["gaming highlights", "gaming setup", "game clips", "esports tiktok"],
    "Music":          ["singing cover", "original song", "music producer", "song lyrics"],
    "Dance":          ["dance challenge", "dance tutorial", "viral dance", "dance trend"],
    "Tech":           ["tech review", "new gadgets", "iphone tips", "tech unboxing"],
    "Finance":        ["investing for beginners", "stock market tips", "personal finance", "budgeting tips"],
    "Money":          ["how to make money", "money tips", "saving money hacks", "side income"],
    "Side Hustles":   ["side hustle ideas", "make money online", "passive income", "work from home"],
    "Crypto":         ["crypto tips", "bitcoin explained", "web3 beginners", "crypto trading"],
    "Business":       ["entrepreneur tips", "small business", "startup advice", "business hack"],
    "Health":         ["wellness routine", "healthy lifestyle", "health tips", "self care"],
    "Mental Health":  ["mental health tips", "anxiety advice", "therapy talk", "emotional healing"],
    "Yoga":           ["yoga flow", "morning yoga", "meditation guide", "yoga for beginners"],
    "Travel":         ["travel vlog", "travel tips", "hidden gems", "solo travel"],
    "Lifestyle":      ["day in my life", "morning routine", "lifestyle vlog", "weekly vlog"],
    "Motivation":     ["motivation speech", "mindset tips", "self improvement", "daily habits"],
    "Sports":         ["sports highlights", "athlete training", "extreme sports", "basketball tiktok"],
    "Dating":         ["relationship advice", "dating tips", "couples goals", "love advice"],
    "Art":            ["art process", "drawing tutorial", "digital art", "art timelapse"],
    "Pets":           ["dog training", "cute cat", "funny pets", "pet care tips"],
    "Parenting":      ["mom life", "parenting tips", "baby milestone", "family vlog"],
    "Kids":           ["baby milestone", "toddler activities", "newborn tips", "kids tiktok"],
    "Vegan":          ["vegan recipe", "plant based meal", "vegan lifestyle", "vegan cooking"],
    "DIY & Crafts":   ["diy project", "craft ideas", "handmade tiktok", "thrift flip"],
    "Home Decor":     ["home decor ideas", "room makeover", "apartment tour", "interior design"],
    "Cleaning":       ["cleaning motivation", "clean with me", "declutter tips", "organization hack"],
    "Career":         ["job interview tips", "career advice", "resume tips", "work tips"],
    "Real Estate":    ["real estate tips", "house tour", "property investment", "first home buyer"],
    "Outdoors":       ["hiking adventure", "camping tips", "nature walk", "trail running"],
    "True Crime":     ["true crime story", "unsolved mystery", "crime documentary", "cold case"],
    "Books":          ["book recommendations", "booktok", "reading vlog", "book review"],
    "Spirituality":   ["astrology reading", "tarot reading", "manifestation tips", "law of attraction"],
    "Movies & TV":    ["movie recommendation", "netflix review", "tv show reaction", "movie analysis"],
    "Anime":          ["anime recommendations", "anime edit", "anime moments", "anime review"],
    "Edits":          ["tiktok edit", "fan edit", "velocity edit", "after effects edit"],
    "Cars":           ["car review", "car modification", "car tips", "dream car tiktok"],
    "Photography":    ["photography tips", "photo editing tutorial", "camera settings", "lightroom tips"],
    "Sustainability": ["sustainable living", "zero waste tips", "eco friendly", "thrift shopping"],
    "College":        ["college tips", "student life", "dorm room tour", "study hack"],
    "Luxury":         ["luxury lifestyle", "rich life", "luxury travel", "expensive tiktok"],
    "Thrifting":      ["thrift haul", "street fashion", "vintage finds", "thrift flip outfit"],
    "Hair":           ["hair tutorial", "hair transformation", "natural hair care", "hairstyle ideas"],
    "Looksmaxxing":   ["looksmaxxing", "glow up tips", "mewing", "how to look better"],
    "ASMR":           ["asmr tiktok", "relaxing video", "satisfying sounds", "sleep sounds"],
    "News":           ["news explained", "political commentary", "current events", "opinion tiktok"],
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
    videos = body.get("data", {}).get("videos", [])
    logger.info("tikwm search '%s' → %d candidates", keyword, len(videos))
    return videos


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
    max_views: Optional[int] = None,
) -> dict:
    keywords = NICHE_KEYWORDS.get(niche, [niche])
    added = skipped = errors = search_failures = gemini_calls = 0
    # Granular skip counters — tell us exactly why candidates were filtered out.
    skip_missing_id = skip_missing_play_url = skip_below_min_views = skip_above_max_views = skip_duplicate = 0
    # Split error counters — separate download vs. Gemini vs. DB failures.
    download_errors = analysis_errors = db_errors = 0
    last_download_error = last_analysis_error = last_db_error = ""
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

            if consecutive_errors >= _CIRCUIT_BREAKER_THRESHOLD:
                logger.warning(
                    "Circuit breaker: stopping niche=%s after %d consecutive errors",
                    niche, consecutive_errors,
                )
                break

            video_id = str(v.get("video_id", ""))
            play_count = int(v.get("play_count") or 0)
            like_count = int(v.get("digg_count") or 0)
            play_url = v.get("play", "")

            # Granular filter — log each skip reason separately.
            if not video_id:
                skip_missing_id += 1
                skipped += 1
                continue
            if not play_url:
                skip_missing_play_url += 1
                skipped += 1
                continue
            if play_count < min_views:
                skip_below_min_views += 1
                skipped += 1
                continue
            if max_views is not None and play_count > max_views:
                skip_above_max_views += 1
                skipped += 1
                continue

            if await _already_harvested(video_id):
                skip_duplicate += 1
                skipped += 1
                continue

            fd, tmp = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            try:
                # Step 1: Download — tracked separately from analysis failures.
                try:
                    await _download(play_url, tmp)
                except Exception as e:
                    msg = str(e)[:200]
                    logger.error("Download error niche=%s vid=%s: %s", niche, video_id, e)
                    download_errors += 1
                    errors += 1
                    consecutive_errors += 1
                    last_download_error = msg
                    continue

                # Step 2: Gemini analysis — tracked separately from download failures.
                gemini_calls += 1
                result = await analyze_seed_video(tmp, "tiktok", niche, play_count, like_count)

                if "error" in result or "seed_quality" not in result:
                    err_msg = str(result.get("error", "missing seed_quality"))[:200]
                    logger.warning("Analysis failed vid:%s — %s", video_id, err_msg)
                    analysis_errors += 1
                    errors += 1
                    consecutive_errors += 1
                    last_analysis_error = err_msg
                    continue

                consecutive_errors = 0  # success — reset the circuit breaker
                rating = max(0, min(10, int(round(float(result["seed_quality"])))))
                caption = str(v.get("title") or "").strip()[:300]
                note_parts = [f"Auto-harvested · keyword: {keyword!r} · vid:{video_id}"]
                if caption:
                    note_parts.append(caption)

                # Step 3: DB insert — tracked separately so a schema error is diagnosable.
                try:
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
                except Exception as e:
                    msg = str(e)[:200]
                    logger.error("DB error niche=%s vid=%s: %s", niche, video_id, e)
                    db_errors += 1
                    errors += 1
                    consecutive_errors += 1
                    last_db_error = msg
                    continue

                added += 1
                logger.info("Harvested niche=%s vid=%s rating=%d views=%d", niche, video_id, rating, play_count)

            except Exception as e:
                # Catch-all for anything not handled above (e.g. rating type error).
                logger.error("Harvest error niche=%s vid=%s: %s", niche, video_id, e)
                errors += 1
                consecutive_errors += 1
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)

    logger.info(
        "harvest_niche done niche=%s added=%d skipped=%d(below_views=%d above_views=%d dup=%d) "
        "search_fail=%d gemini=%d dl_err=%d analysis_err=%d db_err=%d",
        niche, added, skipped, skip_below_min_views, skip_above_max_views, skip_duplicate,
        search_failures, gemini_calls, download_errors, analysis_errors, db_errors,
    )
    return {
        "niche": niche,
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "search_failures": search_failures,
        "gemini_calls": gemini_calls,
        "skip_missing_id": skip_missing_id,
        "skip_missing_play_url": skip_missing_play_url,
        "skip_below_min_views": skip_below_min_views,
        "skip_above_max_views": skip_above_max_views,
        "skip_duplicate": skip_duplicate,
        "download_errors": download_errors,
        "analysis_errors": analysis_errors,
        "db_errors": db_errors,
        "last_download_error": last_download_error,
        "last_analysis_error": last_analysis_error,
        "last_db_error": last_db_error,
    }


async def harvest_all(
    niches: Optional[list[str]] = None,
    min_views: int = DEFAULT_MIN_VIEWS,
    max_per_niche: int = DEFAULT_MAX_PER_NICHE,
    max_views: Optional[int] = None,
) -> None:
    global _last_harvest
    target = niches or list(NICHE_KEYWORDS.keys())
    _last_harvest = {"status": "running", "started_at": datetime.utcnow().isoformat()}
    logger.info("Harvest started: %d niches min_views=%d max_views=%s max_per_niche=%d", len(target), min_views, max_views, max_per_niche)

    try:
        sem = asyncio.Semaphore(_TIKTOK_CONCURRENCY)
        _running: dict = {
            "added": 0, "skipped": 0, "errors": 0, "gemini_calls": 0,
            "search_failures": 0, "niches_done": 0,
            "skip_missing_id": 0, "skip_missing_play_url": 0,
            "skip_below_min_views": 0, "skip_above_max_views": 0, "skip_duplicate": 0,
            "download_errors": 0, "analysis_errors": 0, "db_errors": 0,
            "last_download_error": "", "last_analysis_error": "", "last_db_error": "",
        }

        async def _run(niche: str) -> dict:
            async with sem:
                result = await harvest_niche(niche, min_views, max_per_niche, max_views)
            _running["added"] += result["added"]
            _running["skipped"] += result["skipped"]
            _running["errors"] += result["errors"]
            _running["gemini_calls"] += result.get("gemini_calls", 0)
            _running["search_failures"] += result.get("search_failures", 0)
            _running["skip_missing_id"] += result.get("skip_missing_id", 0)
            _running["skip_missing_play_url"] += result.get("skip_missing_play_url", 0)
            _running["skip_below_min_views"] += result.get("skip_below_min_views", 0)
            _running["skip_above_max_views"] += result.get("skip_above_max_views", 0)
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
            # Update in-memory status live so polling shows progress.
            _last_harvest.update({
                "niches_processed": _running["niches_done"],
                "total_added": _running["added"],
                "total_skipped": _running["skipped"],
                "total_errors": _running["errors"],
                "total_gemini_calls": _running["gemini_calls"],
                "total_search_failures": _running["search_failures"],
                "total_skip_missing_id": _running["skip_missing_id"],
                "total_skip_missing_play_url": _running["skip_missing_play_url"],
                "total_skip_below_min_views": _running["skip_below_min_views"],
                "total_skip_above_max_views": _running["skip_above_max_views"],
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
                logger.error("TikTok niche task crashed: %s", r)

        total_added = _running["added"]
        total_errors = _running["errors"]
        total_search_failures = _running["search_failures"]
        total_gemini_calls = _running["gemini_calls"]

        # Honest status: "degraded" when errors or search failures caused zero results.
        # "done" when seeds were added, or when filters (not errors) caused zero results.
        if total_added == 0 and (total_errors > 0 or total_search_failures > 0):
            final_status = "degraded"
        else:
            final_status = "done"

        _last_harvest = {
            "status": final_status,
            "finished_at": datetime.utcnow().isoformat(),
            "niches_processed": len(results),
            "total_added": total_added,
            "total_skipped": _running["skipped"],
            "total_errors": total_errors,
            "total_gemini_calls": total_gemini_calls,
            "total_search_failures": total_search_failures,
            "total_skip_missing_id": _running["skip_missing_id"],
            "total_skip_missing_play_url": _running["skip_missing_play_url"],
            "total_skip_below_min_views": _running["skip_below_min_views"],
            "total_skip_above_max_views": _running["skip_above_max_views"],
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
            "Harvest done: status=%s added=%d skipped=%d(below_views=%d) "
            "errors=%d(dl=%d analysis=%d db=%d) gemini=%d search_fail=%d failed_niches=%d",
            final_status, total_added, _running["skipped"], _running["skip_below_min_views"],
            total_errors, _running["download_errors"], _running["analysis_errors"], _running["db_errors"],
            total_gemini_calls, total_search_failures, failed_niches,
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
