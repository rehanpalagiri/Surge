"""Fetch like count for a single Instagram Reel via RapidAPI.

Uses the same RAPIDAPI_KEY as the admin seed-from-url endpoint.
"""
import os
import time
from urllib.parse import urlsplit
import httpx
from services.telemetry import record_usage_event

_DEFAULT_IG_HOST = "instagram-reels-downloader-api.p.rapidapi.com"
_DEFAULT_IG_PATH = "/download"


def is_instagram_url(url: str) -> bool:
    try:
        parts = urlsplit((url or "").strip())
        host = (parts.hostname or "").lower()
        valid_host = host in ("instagram.com", "instagr.am") or host.endswith(".instagram.com")
        valid_path = "/reel/" in parts.path.lower() or (host == "instagr.am" and bool(parts.path.strip("/")))
        return parts.scheme in ("http", "https") and valid_host and valid_path
    except ValueError:
        return False


async def fetch_instagram_likes(url: str) -> int:
    """Return the like count for an Instagram Reel URL."""
    api_key = os.getenv("RAPIDAPI_KEY", "")
    if not api_key:
        raise ValueError("Instagram link fetching is not yet configured. Enter your likes manually.")

    ig_host = os.getenv("RAPIDAPI_IG_HOST", _DEFAULT_IG_HOST)
    ig_path = os.getenv("RAPIDAPI_IG_PATH", _DEFAULT_IG_PATH)

    started = time.perf_counter()
    success = False
    error_code = None
    body = None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"https://{ig_host}{ig_path}",
                params={"url": url},
                headers={
                    "X-RapidAPI-Key": api_key,
                    "X-RapidAPI-Host": ig_host,
                },
            )
            r.raise_for_status()
            body = r.json()
        if not body.get("success"):
            raise ValueError(body.get("message") or "Couldn't fetch that Reel — check the link and try again.")
        data = body.get("data") or {}
        if data.get("like_count") is None:
            raise ValueError("Instagram provider returned no like count for this Reel.")
        success = True
        return int(data["like_count"])
    except Exception as exc:
        error_code = type(exc).__name__
        raise
    finally:
        await record_usage_event(
            operation="fetch_post_metrics", provider="rapidapi_instagram",
            success=success, latency_ms=(time.perf_counter() - started) * 1000,
            output_bytes=len(str(body).encode("utf-8")) if body is not None else None,
            error_code=error_code,
        )
