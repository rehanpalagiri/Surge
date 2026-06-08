import os
import uuid
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import SeedVideo, UserAnalysis, UserProfile, User
from schemas import AnalysisOut, FeedbackIn, AnalysisSummaryOut
from services.gemini import analyze_video, select_seed_examples
from services.channel_profile import build_channel_profile
from auth import optional_user, require_user

MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB
ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime"}
VALID_MODES = {"quick", "thinking", "deep_thinking"}
MAX_ACTUAL_VIEWS = 500_000_000  # sanity ceiling for feedback (no real video tops this)

router = APIRouter(prefix="/api", tags=["analyze"])


def resolve_mode(requested: str, user, has_usable_seeds: bool, channel_profile) -> str:
    """Authoritative server-side resolution of the EFFECTIVE mode that will run.
    Degrades gracefully so the badge can never overclaim:
      - guests are always Quick;
      - Deep needs a channel profile (>= 2 analyses), else falls back;
      - Thinking/Deep need usable seed buckets, else fall back to Quick.
    """
    if user is None:
        return "quick"
    if requested == "deep_thinking" and channel_profile:
        return "deep_thinking"
    if requested in ("thinking", "deep_thinking") and has_usable_seeds:
        return "thinking"
    return "quick"


@router.post("/analyze", response_model=AnalysisOut)
async def analyze(
    file: UploadFile = File(...),
    niche: str = Form(...),
    caption: str = Form(""),
    bio: str = Form(""),
    platform: str = Form("tiktok"),
    mode: str = Form("quick"),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(optional_user),
):
    platform = platform.lower() if platform.lower() in ("tiktok", "instagram") else "tiktok"
    requested_mode = mode if mode in VALID_MODES else "quick"

    # Validate content type (client-declared; best-effort guard)
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only MP4 and MOV video files are supported.")

    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    # Sanitize filename — strip any path separators the client may have supplied
    original_name = os.path.basename(file.filename or "upload")
    safe_name = f"{uuid.uuid4()}_{original_name}"
    file_path = os.path.join(uploads_dir, safe_name)
    content = await file.read()
    # Enforce size limit server-side (the 100MB UI check is bypassed by direct API calls)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 100MB.")
    with open(file_path, "wb") as f:
        f.write(content)

    # --- Seed reference (Thinking / Deep) ---
    high_seeds: list = []
    low_seeds: list = []
    if requested_mode in ("thinking", "deep_thinking") and user:
        seeds_result = await db.execute(
            select(SeedVideo).where(SeedVideo.platform == platform)
        )
        seeds = seeds_result.scalars().all()
        high_seeds, low_seeds = select_seed_examples(seeds, niche)
    has_usable_seeds = bool(high_seeds or low_seeds)

    # --- Creator channel profile (Deep only, needs >= 2 prior analyses) ---
    channel_profile = None
    if requested_mode == "deep_thinking" and user:
        hist_result = await db.execute(
            select(UserAnalysis).where(
                UserAnalysis.user_id == user.id,
                UserAnalysis.platform == platform,
            )
        )
        channel_profile = build_channel_profile(hist_result.scalars().all())

    effective_mode = resolve_mode(requested_mode, user, has_usable_seeds, channel_profile)

    # Build saved-profile context (name/handle/niche/bio/audience). The prompt builder
    # only injects it for Thinking/Deep, so Quick stays a pure video assessment.
    profile_context = ""
    if user and effective_mode in ("thinking", "deep_thinking"):
        prof_result = await db.execute(
            select(UserProfile).where(
                UserProfile.user_id == user.id,
                UserProfile.platform == platform,
            )
        )
        prof = prof_result.scalar_one_or_none()
        if prof:
            parts = []
            if prof.display_name:
                parts.append(f"Creator name: {prof.display_name}")
            if prof.handle:
                parts.append(f"Handle: @{prof.handle.lstrip('@')}")
            if prof.niche:
                parts.append(f"Primary niche: {prof.niche}")
            if prof.bio:
                parts.append(f"Profile bio: {prof.bio}")
            if prof.target_audience:
                parts.append(f"Target audience: {prof.target_audience}")
            profile_context = "\n".join(parts)

    # Scope the heavy context to the effective mode.
    seeds_high = high_seeds if effective_mode in ("thinking", "deep_thinking") else []
    seeds_low = low_seeds if effective_mode in ("thinking", "deep_thinking") else []
    profile_arg = channel_profile if effective_mode == "deep_thinking" else None

    try:
        result = await analyze_video(
            file_path,
            niche,
            seeds_high,
            seeds_low,
            caption,
            bio,
            platform,
            profile_context,
            profile_arg,
            effective_mode,
        )
    finally:
        # Remove the temp upload — the video has already been sent to Gemini,
        # so we don't need to keep it on the server's disk.
        try:
            os.remove(file_path)
        except OSError:
            pass

    analysis = UserAnalysis(
        user_id=user.id if user else None,
        platform=platform,
        filename=safe_name,
        niche=niche,
        caption=caption or None,
        bio=bio or None,
        scores_json=json.dumps(result),
        verdict=result.get("verdict", "Needs work"),
        mode=effective_mode,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)

    return _to_out(analysis)


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
async def get_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(optional_user),
):
    result = await db.execute(
        select(UserAnalysis).where(UserAnalysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    # Anonymous users always get the locked view.
    # Authenticated users only get the full view for their OWN analyses.
    # If the analysis hasn't been claimed yet (user_id is None), treat as locked
    # for everyone except the eventual owner (they'll claim then re-fetch).
    if user is None or (analysis.user_id is not None and analysis.user_id != user.id):
        return _to_locked(analysis)
    return _to_out(analysis)


@router.get("/me/analyses", response_model=list[AnalysisSummaryOut])
async def my_analyses(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    result = await db.execute(
        select(UserAnalysis)
        .where(UserAnalysis.user_id == user.id)
        .order_by(UserAnalysis.created_at.desc())
    )
    analyses = result.scalars().all()
    out = []
    for a in analyses:
        try:
            scores = json.loads(a.scores_json)
        except (ValueError, TypeError):
            scores = {}
        caption_preview = None
        if a.caption:
            caption_preview = a.caption[:80] + ("…" if len(a.caption) > 80 else "")
        out.append(
            {
                "id": a.id,
                "platform": a.platform,
                "niche": a.niche,
                "verdict": a.verdict,
                "overall_score": scores.get("overall_score"),
                "predicted_views": scores.get("predicted_views"),
                "caption_preview": caption_preview,
                "actual_views": a.actual_views,
                "actual_likes": a.actual_likes,
                "mode": a.mode or "quick",
                "created_at": a.created_at,
            }
        )
    return out


@router.post("/analyses/{analysis_id}/claim", response_model=AnalysisOut)
async def claim_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    result = await db.execute(
        select(UserAnalysis).where(UserAnalysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id is None:
        analysis.user_id = user.id
        await db.commit()
        await db.refresh(analysis)
    elif analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="This analysis belongs to another account")
    return _to_out(analysis)


@router.patch("/analyses/{analysis_id}/feedback", response_model=AnalysisOut)
async def submit_feedback(
    analysis_id: int,
    feedback: FeedbackIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    result = await db.execute(
        select(UserAnalysis).where(UserAnalysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    # Only the analysis owner can submit feedback
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this analysis")

    # Hard sanity blocks — keep impossible numbers out of the channel-profile anchor.
    if feedback.actual_views < 0:
        raise HTTPException(status_code=400, detail="Views can't be negative.")
    if feedback.actual_views > MAX_ACTUAL_VIEWS:
        raise HTTPException(status_code=400, detail="That view count is too high to be real.")
    if feedback.actual_likes is not None:
        if feedback.actual_likes < 0:
            raise HTTPException(status_code=400, detail="Likes can't be negative.")
        if feedback.actual_likes > feedback.actual_views:
            raise HTTPException(status_code=400, detail="Likes can't exceed views.")

    analysis.actual_views = feedback.actual_views
    if feedback.actual_likes is not None:
        analysis.actual_likes = feedback.actual_likes
    await db.commit()
    await db.refresh(analysis)
    return _to_out(analysis)


@router.delete("/analyses/{analysis_id}", status_code=204)
async def delete_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    result = await db.execute(
        select(UserAnalysis).where(UserAnalysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this analysis")
    await db.delete(analysis)
    await db.commit()


def _to_out(analysis: UserAnalysis) -> dict:
    return {
        "id": analysis.id,
        "platform": analysis.platform or "tiktok",
        "filename": analysis.filename,
        "niche": analysis.niche,
        "caption": analysis.caption,
        "bio": analysis.bio,
        "scores_json": json.loads(analysis.scores_json),
        "verdict": analysis.verdict,
        "actual_views": analysis.actual_views,
        "actual_likes": analysis.actual_likes,
        "mode": analysis.mode or "quick",
        "created_at": analysis.created_at,
    }


def _to_locked(analysis: UserAnalysis) -> dict:
    """Anonymous (free-tier) view: only the headline prediction is exposed.
    All locked fields are stripped server-side, not just hidden in the UI."""
    try:
        scores = json.loads(analysis.scores_json)
    except (ValueError, TypeError):
        scores = {}
    return {
        "id": analysis.id,
        "platform": analysis.platform or "tiktok",
        "filename": analysis.filename,
        "niche": analysis.niche,
        "caption": None,
        "bio": None,
        "scores_json": {
            "verdict": scores.get("verdict", analysis.verdict),
            "predicted_views": scores.get("predicted_views", "Unknown"),
            "locked": True,
        },
        "verdict": analysis.verdict,
        "actual_views": None,
        "actual_likes": None,
        "mode": analysis.mode or "quick",
        "created_at": analysis.created_at,
    }
