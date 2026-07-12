"""Fetch like count for a single Instagram Reel.

Primary: RapidAPI (RAPIDAPI_KEY + configurable host/path).
Fallback: HikerAPI (HIKERAPI_KEY) via /v1/media/by/shortcode.
"""
import logging
import os
import time
from urllib.parse import urlsplit
import httpx
from services.telemetry import record_usage_event

log = logging.getLogger("instagram_fetch")

_DEFAULT_IG_HOST = "instagram-reels-downloader-api.p.rapidapi.com"
_DEFAULT_IG_PATH = "/download"
_HIKERAPI_BASE = "https://api.hikerapi.com"


def _status_error_code(exc: Exception) -> str:
    """Prefer http_<status> for a non-2xx so telemetry shows the provider status,
    not just the exception class."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return f"http_{exc.response.status_code}"
    return type(exc).__name__


def is_instagram_url(url: str) -> bool:
    try:
        parts = urlsplit((url or "").strip())
        host = (parts.hostname or "").lower()
        valid_host = host in ("instagram.com", "instagr.am") or host.endswith(".instagram.com")
        valid_path = "/reel/" in parts.path.lower() or (host == "instagr.am" and bool(parts.path.strip("/")))
        return parts.scheme in ("http", "https") and valid_host and valid_path
    except ValueError:
        return False


def _shortcode_from_url(url: str) -> str | None:
    """Extract the Reel shortcode from an Instagram URL.
    URL formats: /reel/{code}/ or /p/{code}/
    """
    try:
        parts = urlsplit(url.strip())
        segs = [s for s in parts.path.split("/") if s]
        # ['reel', 'DXC-Lp_Ef83'] → 'DXC-Lp_Ef83'
        if len(segs) >= 2 and segs[-2] in ("reel", "p", "tv"):
            return segs[-1]
        if len(segs) >= 1:
            return segs[-1]
    except Exception:
        pass
    return None


async def _fetch_via_rapidapi(url: str, api_key: str) -> int:
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
        error_code = _status_error_code(exc)
        raise
    finally:
        await record_usage_event(
            operation="fetch_post_metrics", provider="rapidapi_instagram",
            success=success, latency_ms=(time.perf_counter() - started) * 1000,
            output_bytes=len(str(body).encode("utf-8")) if body is not None else None,
            error_code=error_code,
        )


async def _fetch_via_hikerapi(url: str) -> int:
    """Fallback: fetch likes via HikerAPI /v1/media/by/shortcode."""
    key = os.getenv("HIKERAPI_KEY", "")
    if not key:
        raise ValueError("HIKERAPI_KEY is not configured.")
    shortcode = _shortcode_from_url(url)
    if not shortcode:
        raise ValueError("Could not extract shortcode from Instagram URL.")
    started = time.perf_counter()
    success = False
    error_code = None
    body = None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{_HIKERAPI_BASE}/v1/media/by/shortcode",
                params={"code": shortcode},
                headers={"x-access-key": key, "accept": "application/json"},
            )
            r.raise_for_status()
            body = r.json()
        like_count = body.get("like_count")
        if like_count is None:
            raise ValueError("HikerAPI did not return a like count for this Reel.")
        success = True
        return int(like_count)
    except Exception as exc:
        error_code = _status_error_code(exc)
        raise
    finally:
        await record_usage_event(
            operation="fetch_post_metrics", provider="hikerapi_instagram",
            success=success, latency_ms=(time.perf_counter() - started) * 1000,
            output_bytes=len(str(body).encode("utf-8")) if body is not None else None,
            error_code=error_code,
        )


async def fetch_instagram_likes(url: str) -> int:
    """Return the like count for an Instagram Reel URL.

    Tries RapidAPI first (if RAPIDAPI_KEY is set), then HikerAPI as fallback.
    Raises ValueError if neither provider returns a usable count.
    """
    api_key = os.getenv("RAPIDAPI_KEY", "")
    hikerapi_key = os.getenv("HIKERAPI_KEY", "")

    if not api_key and not hikerapi_key:
        raise ValueError("Instagram link fetching is not configured. Enter your likes manually.")

    primary_err: Exception | None = None

    # Try RapidAPI first
    if api_key:
        try:
            likes = await _fetch_via_rapidapi(url, api_key)
            log.info("instagram fetch ok via rapidapi (likes=%s): %s", likes, url)
            return likes
        except Exception as e:
            log.warning("instagram rapidapi path failed (%s): %s", _status_error_code(e), url)
            primary_err = e

    # Fallback to HikerAPI
    if hikerapi_key:
        try:
            likes = await _fetch_via_hikerapi(url)
            log.info("instagram fetch ok via hikerapi (likes=%s): %s", likes, url)
            return likes
        except Exception as fallback_err:
            log.warning("instagram hikerapi path failed (%s): %s", _status_error_code(fallback_err), url)
            # Both failed — raise the primary error for a more descriptive message
            raise primary_err or fallback_err

    # Only RapidAPI was configured but it failed
    if primary_err:
        raise primary_err

    raise ValueError("Instagram link fetching is not configured.")
