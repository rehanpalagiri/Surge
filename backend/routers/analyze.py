import os
import uuid
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import SeedVideo, UserAnalysis, User
from schemas import AnalysisOut, FeedbackIn, AnalysisSummaryOut
from services.gemini import analyze_video
from auth import optional_user, require_user

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze", response_model=AnalysisOut)
async def analyze(
    file: UploadFile = File(...),
    niche: str = Form(...),
    caption: str = Form(""),
    bio: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(optional_user),
):
    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    safe_name = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(uploads_dir, safe_name)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    seeds_result = await db.execute(select(SeedVideo))
    seeds = seeds_result.scalars().all()

    try:
        result = await analyze_video(file_path, niche, seeds, caption, bio)
    finally:
        # Remove the temp upload — the video has already been sent to Gemini,
        # so we don't need to keep it on the server's disk.
        try:
            os.remove(file_path)
        except OSError:
            pass

    analysis = UserAnalysis(
        user_id=user.id if user else None,
        filename=safe_name,
        niche=niche,
        caption=caption or None,
        bio=bio or None,
        scores_json=json.dumps(result),
        verdict=result.get("verdict", "Needs work"),
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
    if user is None:
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
                "niche": a.niche,
                "verdict": a.verdict,
                "overall_score": scores.get("overall_score"),
                "caption_preview": caption_preview,
                "actual_views": a.actual_views,
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
):
    result = await db.execute(
        select(UserAnalysis).where(UserAnalysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    analysis.actual_views = feedback.actual_views
    await db.commit()
    await db.refresh(analysis)
    return _to_out(analysis)


def _to_out(analysis: UserAnalysis) -> dict:
    return {
        "id": analysis.id,
        "filename": analysis.filename,
        "niche": analysis.niche,
        "caption": analysis.caption,
        "bio": analysis.bio,
        "scores_json": json.loads(analysis.scores_json),
        "verdict": analysis.verdict,
        "actual_views": analysis.actual_views,
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
        "created_at": analysis.created_at,
    }
