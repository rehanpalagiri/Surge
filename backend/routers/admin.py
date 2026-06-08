import os
import json
import uuid
import hmac
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from typing import Optional

import yt_dlp
from yt_dlp.utils import DownloadError

from database import get_db
from models import SeedVideo, FetchStatus
from schemas import SeedVideoOut
from services.seed_analysis import analyze_seed_video

router = APIRouter(prefix="/api/admin", tags=["admin"])


def check_admin(x_admin_password: Optional[str] = Header(None)):
    expected = os.getenv("ADMIN_PASSWORD", "viraliq-admin")
    # Use constant-time comparison to prevent timing-based password enumeration
    if not x_admin_password or not hmac.compare_digest(x_admin_password, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing admin password")


async def _analyze_and_persist_seed(
    db: AsyncSession,
    file_path: str,
    safe_name: str,
    platform: str,
    niche: str,
    view_count: int,
    like_count: int,
    notes: Optional[str],
    posted_at: Optional[datetime],
) -> SeedVideo:
    """Run the seed-analysis prompt, then persist the seed with its rating + JSON.
    The local file is always deleted (the JSON is the durable artifact). If the
    analysis fails or returns no usable rating, NOTHING is persisted and a 502 is
    raised so the admin can retry — a seed with a null rating must never be created.
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


@router.post("/seed", response_model=SeedVideoOut)
async def add_seed_video(
    file: UploadFile = File(...),
    platform: str = Form("tiktok"),
    niche: str = Form(...),
    view_count: int = Form(...),
    like_count: int = Form(...),
    notes: Optional[str] = Form(None),
    posted_at: Optional[str] = Form(None),  # ISO date string e.g. "2025-03-15"
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
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
            pass  # ignore bad date — field is optional

    platform = platform.lower() if platform.lower() in ("tiktok", "instagram") else "tiktok"
    # Analyzes the video with Gemini, stores the causal writeup + rating, deletes the
    # file. Raises 502 (and saves nothing) if the analysis can't produce a rating.
    return await _analyze_and_persist_seed(
        db, file_path, safe_name, platform, niche, view_count, like_count, notes, parsed_posted_at
    )


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
# Auto-fetch seed videos from a TikTok link (local use — TikTok blocks
# datacenter IPs, so this is not reliable in production).
# ---------------------------------------------------------------------------

def _looks_like_tiktok(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith(("http://", "https://")) and "tiktok.com" in u


def _yt_download(url: str, uploads_dir: str, prefix: str):
    """Synchronous yt-dlp download + metadata extraction. Run in a thread."""
    outtmpl = os.path.join(uploads_dir, f"{prefix}_%(id)s.%(ext)s")
    opts = {
        "outtmpl": outtmpl,
        "format": "mp4/bestvideo+bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("requested_downloads"):
            filepath = info["requested_downloads"][0].get("filepath")
        else:
            filepath = ydl.prepare_filename(info)
    return info, filepath


async def _record_status(db: AsyncSession, ok: bool, message: str, url: str):
    db.add(FetchStatus(ok=ok, message=message, url=url))
    await db.commit()


@router.post("/seed/from-url", response_model=SeedVideoOut)
async def seed_from_url(
    url: str = Form(...),
    niche: str = Form(...),
    platform: str = Form("tiktok"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    if not _looks_like_tiktok(url):
        # Clearly malformed/unsupported — user error, not a scraper failure.
        raise HTTPException(
            status_code=400,
            detail="Couldn't read that link — check it's a public TikTok URL",
        )

    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    prefix = str(uuid.uuid4())

    try:
        info, filepath = await asyncio.to_thread(
            _yt_download, url, uploads_dir, prefix
        )
    except DownloadError as e:
        # Scraper-broken: extractor error / 403 / 429 / "unable to extract".
        await _record_status(db, ok=False, message=str(e), url=url)
        raise HTTPException(
            status_code=502,
            detail="Auto-fetch failed — TikTok may have changed. See the admin warning banner.",
        )
    except Exception as e:  # noqa: BLE001 — any other extraction failure is scraper-broken too
        await _record_status(db, ok=False, message=str(e), url=url)
        raise HTTPException(
            status_code=502,
            detail="Auto-fetch failed — TikTok may have changed. See the admin warning banner.",
        )

    # The scraper itself succeeded — record health now, before the (separate) Gemini
    # analysis step. A later Gemini failure is not a scraper failure.
    await _record_status(db, ok=True, message="ok", url=url)

    view_count = info.get("view_count") or 0
    like_count = info.get("like_count") or 0
    description = (info.get("description") or "").strip()
    notes = f"Caption: {description}" if description else None

    # yt-dlp returns upload_date as "YYYYMMDD" string
    posted_at = None
    raw_date = info.get("upload_date")
    if raw_date:
        try:
            posted_at = datetime.strptime(raw_date, "%Y%m%d")
        except ValueError:
            pass

    platform = platform.lower() if platform.lower() in ("tiktok", "instagram") else "tiktok"
    safe_name = os.path.basename(filepath) if filepath else f"{prefix}.mp4"
    analyze_path = filepath if filepath else os.path.join(uploads_dir, safe_name)
    # Same pipeline as a manual upload: analyze → store rating + JSON → delete file.
    return await _analyze_and_persist_seed(
        db, analyze_path, safe_name, platform, niche, view_count, like_count, notes, posted_at
    )


@router.get("/fetch-status")
async def get_fetch_status(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    # Look at the single most recent attempt: a later success (or an ack)
    # clears the broken state.
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
