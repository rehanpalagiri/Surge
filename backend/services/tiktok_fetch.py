"""Fetch public TikTok video metadata via tikwm.com (free, keyless, works from
any IP). Shared by the admin seed fetcher and the user video-link endpoint.
"""
from datetime import datetime, timezone
import hashlib
import json
import time
from urllib.parse import urlsplit

import httpx
from services.telemetry import record_usage_event

MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


def _optional_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_tiktok_url(url: str) -> bool:
    try:
        parts = urlsplit((url or "").strip())
        host = (parts.hostname or "").lower()
        return parts.scheme in ("http", "https") and (host == "tiktok.com" or host.endswith(".tiktok.com"))
    except ValueError:
        return False


async def fetch_tiktok(url: str) -> dict:
    """Fetch TikTok video metadata. Raises ValueError on any fetch failure."""
    started = time.perf_counter()
    success = False
    error_code = None
    body = None
    try:
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
        view_count = _optional_int(data.get("play_count"))
        like_count = _optional_int(data.get("digg_count"))
        if view_count is None or like_count is None:
            raise ValueError("tikwm response did not include usable view and like counts")
        posted_at = None
        ts = data.get("create_time")
        if ts:
            try:
                posted_at = datetime.fromtimestamp(int(ts), timezone.utc).replace(tzinfo=None)
            except (ValueError, OSError, OverflowError):
                pass

        success = True
        payload_hash = hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {
            "video_id": str(data.get("id") or data.get("video_id") or "").strip(),
            "video_url": data["play"],
            "view_count": view_count,
            "like_count": like_count,
            "comment_count": _optional_int(data.get("comment_count")),
            "share_count": _optional_int(data.get("share_count")),
            "save_count": _optional_int(data.get("collect_count")),
            "caption": str(data.get("title") or "").strip()[:2200],
            "posted_at": posted_at,
            "author_handle": str((data.get("author") or {}).get("unique_id") or "").strip(),
            "creator_followers": _optional_int((data.get("author") or {}).get("follower_count")),
            "provider_payload_hash": payload_hash,
        }
    except Exception as exc:
        error_code = type(exc).__name__
        raise
    finally:
        await record_usage_event(
            operation="fetch_post_metrics", provider="tikwm", success=success,
            latency_ms=(time.perf_counter() - started) * 1000,
            output_bytes=len(str(body).encode("utf-8")) if body is not None else None,
            error_code=error_code,
        )


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
