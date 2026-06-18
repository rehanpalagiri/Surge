"""Fetch public TikTok video metadata via tikwm.com (free, keyless, works from
any IP). Shared by the admin seed fetcher and the user video-link endpoint.
"""
from datetime import datetime

import httpx

MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


def is_tiktok_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith(("http://", "https://")) and "tiktok.com" in u


async def fetch_tiktok(url: str) -> dict:
    """Fetch TikTok video metadata. Raises ValueError on any fetch failure."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            "https://www.tikwm.com/api/",
            params={"url": url},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()
        body = r.json()

    if body.get("code") != 0:
        raise ValueError(f"tikwm: {body.get('msg', 'unknown error')}")

    data = body["data"]
    posted_at = None
    ts = data.get("create_time")
    if ts:
        try:
            posted_at = datetime.fromtimestamp(int(ts))
        except (ValueError, OSError, OverflowError):
            pass

    return {
        "video_url": data["play"],
        "view_count": int(data.get("play_count") or 0),
        "like_count": int(data.get("digg_count") or 0),
        "caption": str(data.get("title") or "").strip()[:2200],
        "posted_at": posted_at,
        # @handle of the uploader — used for the soft ownership check
        "author_handle": str((data.get("author") or {}).get("unique_id") or "").strip(),
    }


async def download_tiktok_video(tiktok_url: str) -> tuple[bytes, str]:
    """Download a TikTok video's bytes. Returns (video_bytes, caption).
    Raises ValueError on fetch failure, or if the downloaded file exceeds 100 MB."""
    meta = await fetch_tiktok(tiktok_url)
    play_url = meta["video_url"]
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(play_url, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
    if len(r.content) > MAX_DOWNLOAD_BYTES:
        raise ValueError("Video exceeds 100 MB — try a shorter clip.")
    return r.content, meta.get("caption", "")
