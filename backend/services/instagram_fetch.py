"""Fetch like count for a single Instagram Reel via RapidAPI.

Uses the same RAPIDAPI_KEY as the admin seed-from-url endpoint.
"""
import os
import httpx

_DEFAULT_IG_HOST = "instagram-reels-downloader-api.p.rapidapi.com"
_DEFAULT_IG_PATH = "/download"


def is_instagram_url(url: str) -> bool:
    return "instagram.com/reel/" in url or "instagr.am" in url


async def fetch_instagram_likes(url: str) -> int:
    """Return the like count for an Instagram Reel URL."""
    api_key = os.getenv("RAPIDAPI_KEY", "")
    if not api_key:
        raise ValueError("Instagram link fetching is not yet configured. Enter your likes manually.")

    ig_host = os.getenv("RAPIDAPI_IG_HOST", _DEFAULT_IG_HOST)
    ig_path = os.getenv("RAPIDAPI_IG_PATH", _DEFAULT_IG_PATH)

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
    return int(data.get("like_count") or 0)
