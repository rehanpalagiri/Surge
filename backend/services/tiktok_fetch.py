"""Fetch public TikTok video metadata via tikwm.com (free, keyless, works from
any IP). Shared by the admin seed fetcher and the user video-link endpoint.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import time
from urllib.parse import urlsplit

import httpx
from services.telemetry import record_usage_event

log = logging.getLogger("tiktok_fetch")

MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # 100 MB

# tikwm is a free, keyless, shared endpoint — it rate-limits (429) aggressively
# from datacenter IPs (e.g. Railway egress) and occasionally 5xx-es under load. A
# bounded retry with exponential backoff rides out the transient cases; a terminal
# non-2xx is surfaced with its status code + a body snippet so the collector's
# last_error is diagnosable instead of a bare "HTTPStatusError".
_RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0


def _body_snippet(response: httpx.Response, limit: int = 200) -> str:
    """Whitespace-collapsed, length-capped body text for error diagnostics."""
    try:
        text = response.text or ""
    except Exception:
        return ""
    return " ".join(text.split())[:limit]


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
    """Fetch TikTok video metadata via tikwm.com. Raises ValueError on any fetch
    failure, with the HTTP status + a response-body snippet in the message so a
    caller (e.g. the outcome collector) records a diagnosable last_error rather
    than just the exception class."""
    started = time.perf_counter()
    success = False
    error_code = None
    body = None
    last_status = None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                r = await client.get(
                    "https://www.tikwm.com/api/",
                    params={"url": url},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                last_status = r.status_code
                if r.status_code in _RETRY_STATUSES and attempt < _MAX_ATTEMPTS:
                    backoff = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    log.warning(
                        "tikwm HTTP %s (attempt %d/%d) — backing off %.1fs: %s",
                        r.status_code, attempt, _MAX_ATTEMPTS, backoff, url,
                    )
                    await asyncio.sleep(backoff)
                    continue
                break

        if r.status_code >= 400:
            error_code = f"http_{r.status_code}"
            snippet = _body_snippet(r)
            raise ValueError(
                f"tikwm blocked or errored (HTTP {r.status_code})"
                + (f": {snippet}" if snippet else "")
            )
        body = r.json()

        if body.get("code") != 0:
            error_code = "tikwm_nonzero_code"
            raise ValueError(f"tikwm: {body.get('msg', 'unknown error')}")

        data = body["data"]
        view_count = _optional_int(data.get("play_count"))
        like_count = _optional_int(data.get("digg_count"))
        if view_count is None or like_count is None:
            error_code = "missing_counts"
            raise ValueError("tikwm response did not include usable view and like counts")
        posted_at = None
        ts = data.get("create_time")
        if ts:
            try:
                posted_at = datetime.fromtimestamp(int(ts), timezone.utc).replace(tzinfo=None)
            except (ValueError, OSError, OverflowError):
                pass

        success = True
        log.info("tikwm fetch ok (views=%s likes=%s): %s", view_count, like_count, url)
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
        # Preserve a precise code already set above (http_<status>, tikwm_*,
        # missing_counts); fall back to the exception class for transport errors
        # (timeouts, connection resets), appending the last HTTP status if known.
        if error_code is None:
            error_code = type(exc).__name__
            if last_status is not None:
                error_code = f"{error_code}:{last_status}"
        log.warning("tikwm fetch failed (%s): %s — %s", error_code, url, exc)
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
