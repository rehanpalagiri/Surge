import os
import json
import uuid
import hmac
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func

from database import get_db
from models import SeedVideo, FetchStatus
from schemas import SeedVideoOut
from services.seed_analysis import analyze_seed_video
from services.tiktok_fetch import fetch_tiktok

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def check_admin(x_admin_password: Optional[str] = Header(None)):
    expected = os.getenv("ADMIN_PASSWORD", "viraliq-admin")
    if not x_admin_password or not hmac.compare_digest(x_admin_password, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing admin password")


# ---------------------------------------------------------------------------
# Shared seed persist helper
# ---------------------------------------------------------------------------

async def _analyze_and_persist_seed(
    db: AsyncSession,
    file_path: str,
    safe_name: str,
    platform: str,
    niche: str,
    view_count: Optional[int],   # None for Instagram (platform hides views)
    like_count: int,
    notes: Optional[str],
    posted_at: Optional[datetime],
) -> SeedVideo:
    """Run the seed-analysis prompt, then persist the seed with its rating + JSON.
    The local file is always deleted (the JSON is the durable artifact). If the
    analysis fails or returns no usable rating, NOTHING is persisted and a 502 is
    raised so the admin can retry.
    """
    try:
        result = await analyze_seed_video(file_path, platform, niche, view_count, like_count)
    finally:
        try:
            os.remove(file_path)
        except OSError:
            pass

    if not isinstance(result, dict) or "error" in result or "virality_rating" not in result:
        detail = result.get("error", "invalid response") if isinstance(result, dict) else "invalid response"
        raise HTTPException(
            status_code=502,
            detail=f"Seed analysis failed ({detail}). Seed was NOT saved — please try again.",
        )

    try:
        rating = max(0, min(10, int(round(float(result["virality_rating"])))))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="Seed analysis returned an invalid rating. Seed was NOT saved — please try again.",
        )

    seed = SeedVideo(
        filename=safe_name,
        platform=platform,
        niche=niche,
        view_count=view_count,
        like_count=like_count,
        rating=rating,
        gemini_analysis=json.dumps(result),
        notes=notes,
        posted_at=posted_at,
    )
    db.add(seed)
    await db.commit()
    await db.refresh(seed)
    return seed


# ---------------------------------------------------------------------------
# Manual upload
# ---------------------------------------------------------------------------

@router.post("/seed", response_model=SeedVideoOut)
async def add_seed_video(
    file: UploadFile = File(...),
    platform: str = Form("tiktok"),
    niche: str = Form(...),
    view_count: Optional[int] = Form(None),   # required for TikTok, not for Instagram
    like_count: int = Form(...),
    notes: Optional[str] = Form(None),
    posted_at: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    platform = platform.lower() if platform.lower() in ("tiktok", "instagram") else "tiktok"

    if platform == "tiktok" and view_count is None:
        raise HTTPException(status_code=422, detail="view_count is required for TikTok seeds.")

    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    original_name = os.path.basename(file.filename or "upload")
    safe_name = f"{uuid.uuid4()}_{original_name}"
    file_path = os.path.join(uploads_dir, safe_name)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    parsed_posted_at = None
    if posted_at:
        try:
            parsed_posted_at = datetime.fromisoformat(posted_at)
        except ValueError:
            pass

    return await _analyze_and_persist_seed(
        db, file_path, safe_name, platform, niche, view_count, like_count, notes, parsed_posted_at
    )


# ---------------------------------------------------------------------------
# Seed list + delete
# ---------------------------------------------------------------------------

@router.get("/seeds", response_model=list[SeedVideoOut])
async def get_seeds(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    result = await db.execute(select(SeedVideo).order_by(SeedVideo.created_at.desc()))
    return result.scalars().all()


@router.delete("/seeds/{seed_id}")
async def delete_seed(
    seed_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    result = await db.execute(select(SeedVideo).where(SeedVideo.id == seed_id))
    seed = result.scalar_one_or_none()
    if not seed:
        raise HTTPException(status_code=404, detail="Seed video not found")
    await db.execute(delete(SeedVideo).where(SeedVideo.id == seed_id))
    await db.commit()
    return {"deleted": seed_id}


# ---------------------------------------------------------------------------
# URL-based fetchers (tikwm.com for TikTok, EaseApi for Instagram)
# ---------------------------------------------------------------------------

def _detect_platform(url: str) -> Optional[str]:
    u = (url or "").strip().lower()
    if not u.startswith(("http://", "https://")):
        return None
    if "tiktok.com" in u:
        return "tiktok"
    if "instagram.com" in u or "instagr.am" in u:
        return "instagram"
    return None


async def _fetch_instagram(url: str) -> dict:
    """Fetch Instagram Reel via EaseApi on RapidAPI.
    view_count is always None — Instagram does not expose it publicly.
    Requires RAPIDAPI_KEY env var. Host/path can be overridden with
    RAPIDAPI_IG_HOST / RAPIDAPI_IG_PATH env vars.
    """
    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        raise ValueError("RAPIDAPI_KEY is not configured. Add it to your environment variables.")

    ig_host = os.getenv("RAPIDAPI_IG_HOST", "instagram-reels-downloader-api.p.rapidapi.com")
    ig_path = os.getenv("RAPIDAPI_IG_PATH", "/download")

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
        raise ValueError(f"Instagram API: {body.get('message', 'unknown error')}")

    data = body.get("data") or {}

    # Find the video download URL in the medias array (type == "video")
    video_url = None
    for m in (data.get("medias") or []):
        if isinstance(m, dict) and m.get("type") == "video" and m.get("url"):
            video_url = m["url"]
            break

    if not video_url:
        raise ValueError("Instagram API returned no video download URL")

    return {
        "video_url": video_url,
        "view_count": None,   # Instagram never exposes views publicly
        "like_count": int(data.get("like_count") or 0),
        "caption": str(data.get("title") or "").strip()[:2200],
        "posted_at": None,
    }


async def _download_video(video_url: str, file_path: str) -> None:
    """Stream-download a video to disk."""
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            async with client.stream("GET", video_url) as r:
                r.raise_for_status()
                with open(file_path, "wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
    except httpx.HTTPError as e:
        raise ValueError(f"Video download failed: {e}") from e


async def _record_status(db: AsyncSession, ok: bool, message: str, url: str):
    db.add(FetchStatus(ok=ok, message=message, url=url))
    await db.commit()


# ---------------------------------------------------------------------------
# Fetch from URL endpoint
# ---------------------------------------------------------------------------

@router.post("/seed/from-url", response_model=SeedVideoOut)
async def seed_from_url(
    url: str = Form(...),
    niche: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    platform = _detect_platform(url)
    if not platform:
        raise HTTPException(
            status_code=400,
            detail="Couldn't read that link — check it's a public TikTok or Instagram URL.",
        )

    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    prefix = str(uuid.uuid4())

    try:
        if platform == "tiktok":
            meta = await fetch_tiktok(url)
        else:
            meta = await _fetch_instagram(url)
    except Exception as e:
        await _record_status(db, ok=False, message=str(e), url=url)
        raise HTTPException(status_code=502, detail=f"Auto-fetch failed: {e}")

    await _record_status(db, ok=True, message="ok", url=url)

    safe_name = f"{prefix}.mp4"
    file_path = os.path.join(uploads_dir, safe_name)
    try:
        await _download_video(meta["video_url"], file_path)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    notes = f"Caption: {meta['caption']}" if meta.get("caption") else None

    return await _analyze_and_persist_seed(
        db, file_path, safe_name, platform, niche,
        meta["view_count"], meta["like_count"], notes, meta["posted_at"],
    )


# ---------------------------------------------------------------------------
# Fetch-status banner
# ---------------------------------------------------------------------------

@router.get("/fetch-status")
async def get_fetch_status(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    result = await db.execute(
        select(FetchStatus).order_by(FetchStatus.created_at.desc(), FetchStatus.id.desc())
    )
    latest = result.scalars().first()
    if latest and not latest.ok and not latest.acknowledged:
        return {
            "broken": True,
            "message": latest.message,
            "url": latest.url,
            "when": latest.created_at,
        }
    return {"broken": False}


@router.post("/fetch-status/ack")
async def ack_fetch_status(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    await db.execute(
        update(FetchStatus)
        .where(FetchStatus.ok == False, FetchStatus.acknowledged == False)  # noqa: E712
        .values(acknowledged=True)
    )
    await db.commit()
    return {"acknowledged": True}


# ---------------------------------------------------------------------------
# Instagram API usage counter (20 req/month on EaseApi free tier)
# ---------------------------------------------------------------------------

@router.get("/api-usage")
async def get_api_usage(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """Successful Instagram URL fetches this calendar month vs the 20/month free limit."""
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    resets_at = (
        datetime(now.year + 1, 1, 1) if now.month == 12
        else datetime(now.year, now.month + 1, 1)
    )

    result = await db.execute(
        select(func.count()).select_from(FetchStatus).where(
            FetchStatus.url.ilike("%instagram%"),
            FetchStatus.ok == True,   # noqa: E712
            FetchStatus.created_at >= month_start,
        )
    )
    used = result.scalar() or 0

    return {
        "instagram": {
            "used": used,
            "limit": 20,
            "resets_at": resets_at.strftime("%Y-%m-%d"),
        }
    }
