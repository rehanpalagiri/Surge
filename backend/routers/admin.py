import os
import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from typing import Optional

import yt_dlp
from yt_dlp.utils import DownloadError

from database import get_db
from models import SeedVideo, FetchStatus
from schemas import SeedVideoOut

router = APIRouter(prefix="/api/admin", tags=["admin"])


def check_admin(x_admin_password: Optional[str] = Header(None)):
    expected = os.getenv("ADMIN_PASSWORD", "viraliq-admin")
    if not x_admin_password or x_admin_password != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin password")


@router.post("/seed", response_model=SeedVideoOut)
async def add_seed_video(
    file: UploadFile = File(...),
    niche: str = Form(...),
    view_count: int = Form(...),
    like_count: int = Form(...),
    performed: bool = Form(...),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    safe_name = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(uploads_dir, safe_name)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    seed = SeedVideo(
        filename=safe_name,
        niche=niche,
        view_count=view_count,
        like_count=like_count,
        performed=performed,
        notes=notes,
    )
    db.add(seed)
    await db.commit()
    await db.refresh(seed)
    return seed


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

    view_count = info.get("view_count") or 0
    like_count = info.get("like_count") or 0
    description = (info.get("description") or "").strip()
    notes = f"Caption: {description}" if description else None
    performed = view_count >= 10000

    seed = SeedVideo(
        filename=os.path.basename(filepath) if filepath else f"{prefix}.mp4",
        niche=niche,
        view_count=view_count,
        like_count=like_count,
        performed=performed,
        notes=notes,
    )
    db.add(seed)
    await db.commit()
    await db.refresh(seed)

    await _record_status(db, ok=True, message="ok", url=url)
    return seed


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
