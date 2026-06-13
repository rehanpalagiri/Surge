import os
import uuid
import json
from datetime import datetime, timedelta
from statistics import median
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db
from models import SeedVideo, UserAnalysis, UserProfile, User
from schemas import AnalysisOut, FeedbackIn, AnalysisSummaryOut, VideoLinkIn, SeedConsentDecisionIn
from services.gemini import analyze_video, select_seed_examples
from google.genai.errors import ClientError as _GeminiClientError
from services.channel_profile import build_channel_profile
from services.niche_classifier import classify_niche
from services.tiktok_fetch import fetch_tiktok, is_tiktok_url
from services.seed_promote import promote_analysis_to_seed
from services.rate_limit import get_rate_limit
from auth import optional_user, require_user

MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB
ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime"}
VALID_MODES = {"quick", "thinking", "deep_thinking"}
MAX_ACTUAL_VIEWS = 500_000_000  # sanity ceiling for feedback (no real video tops this)
REFRESH_COOLDOWN = timedelta(hours=24)  # min gap between video-link count refreshes

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

    # Free-text niche: store what the user typed, classify to a canonical
    # niche for seed matching. Truncate before any processing.
    raw_niche = niche.strip()[:200]
    if not raw_niche:
        raise HTTPException(status_code=400, detail="Please provide your content niche.")
    canonical_niche = await classify_niche(raw_niche)

    # Rate limit authenticated users (guests are unmetered)
    if user:
        rl = await get_rate_limit(user.id, db)
        if not rl["allowed"]:
            bonus_tip = " Link a posted video to earn +1 credit." if rl["bonus"] < 10 else ""
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Upload limit reached ({rl['effective_limit']} per {rl['window_hours']}h)."
                    f"{bonus_tip}"
                    + (f" Resets at {rl['resets_at']}." if rl["resets_at"] else "")
                ),
            )

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
        high_seeds, low_seeds = select_seed_examples(seeds, canonical_niche)
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

    # --- Per-creator like baseline (all modes — personalises the 1–10 calibration) ---
    # Uses verified actual_likes from this user's past analyses on this platform.
    # Needs >= 2 data points; falls back to generic calibration otherwise.
    creator_like_baseline: dict | None = None
    if user:
        likes_result = await db.execute(
            select(UserAnalysis.actual_likes).where(
                UserAnalysis.user_id == user.id,
                UserAnalysis.platform == platform,
                UserAnalysis.actual_likes.is_not(None),
            ).order_by(UserAnalysis.created_at.desc()).limit(10)
        )
        past_likes = [r for r in likes_result.scalars().all() if r is not None and r >= 0]
        if len(past_likes) >= 2:
            med = int(median(past_likes))
            creator_like_baseline = {
                "median_likes": med,
                "sample_count": len(past_likes),
                "min_likes": min(past_likes),
                "max_likes": max(past_likes),
            }

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
            canonical_niche,
            seeds_high,
            seeds_low,
            caption,
            bio,
            platform,
            profile_context,
            profile_arg,
            effective_mode,
            niche_raw=raw_niche,
            creator_like_baseline=creator_like_baseline,
        )
    except _GeminiClientError as e:
        if e.code in (429, 403):
            # Gemini quota exhausted or bad API key — return 503 without storing
            # a broken analysis row and without burning a rate-limit credit.
            raise HTTPException(
                status_code=503,
                detail="AI analysis is temporarily unavailable. Please try again in a few minutes.",
            )
        raise
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
        niche=raw_niche,  # the user's own words — what they see in My Projects
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


@router.get("/me/rate-limit")
async def my_rate_limit(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    return await get_rate_limit(user.id, db)


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
                "video_url": a.video_url,
                "counts_fetched_at": a.counts_fetched_at,
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


def _normalize_handle(h: str) -> str:
    return (h or "").strip().lstrip("@").lower()


@router.post("/analyses/{analysis_id}/video-link", response_model=AnalysisOut)
async def link_video(
    analysis_id: int,
    payload: VideoLinkIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Attach the user's posted TikTok link to an analysis and auto-fetch its
    real view/like counts via tikwm. Call with url=None to refresh counts from
    the already-stored link (throttled to once per 24h). TikTok only —
    Instagram has no free uncapped metadata API, so it stays manual entry.
    """
    result = await db.execute(
        select(UserAnalysis).where(UserAnalysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this analysis")
    if (analysis.platform or "tiktok") != "tiktok":
        raise HTTPException(
            status_code=400,
            detail="Auto-fetch only works for TikTok videos — enter Instagram stats manually.",
        )

    new_url = (payload.url or "").strip() or None
    if new_url and not is_tiktok_url(new_url):
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like a TikTok link — paste the URL of your posted video.",
        )
    url = new_url or analysis.video_url
    if not url:
        raise HTTPException(status_code=400, detail="Paste the link to your posted TikTok first.")

    # Throttle pure refreshes (no new link supplied) — counts don't move that fast.
    if not new_url and analysis.counts_fetched_at:
        elapsed = datetime.utcnow() - analysis.counts_fetched_at
        if elapsed < REFRESH_COOLDOWN:
            raise HTTPException(
                status_code=429,
                detail="Stats were refreshed less than 24 hours ago — check back tomorrow.",
            )

    try:
        meta = await fetch_tiktok(url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Couldn't fetch that video: {e}")

    # Soft ownership check: only enforced when BOTH a saved handle and the
    # video's author handle are known. Keeps Deep mode's "verified performance"
    # anchor honest without walling the feature behind profile setup.
    author = _normalize_handle(meta.get("author_handle", ""))
    if author:
        prof_result = await db.execute(
            select(UserProfile).where(
                UserProfile.user_id == user.id,
                UserProfile.platform == "tiktok",
            )
        )
        prof = prof_result.scalar_one_or_none()
        saved = _normalize_handle(prof.handle if prof else "")
        if saved and saved != author:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"That video belongs to @{author}, but your profile handle is @{saved}. "
                    "If that's your account, update your TikTok handle in your profile first."
                ),
            )

    analysis.video_url = url
    analysis.actual_views = meta["view_count"]
    analysis.actual_likes = meta["like_count"]
    analysis.counts_fetched_at = datetime.utcnow()
    await db.commit()
    await db.refresh(analysis)

    # Door B (v1.20): a verified, posted video is the best seed signal there is.
    # Promote it into the reference library in the background so the user's
    # stat-sync stays instant. Idempotent — skipped once already promoted.
    # meta is passed through so the task doesn't hit tikwm again (~1 req/sec cap).
    if analysis.promoted_seed_id is None:
        background_tasks.add_task(promote_analysis_to_seed, analysis.id, meta)

    return _to_out(analysis)


@router.post("/analyses/{analysis_id}/seed-consent", response_model=AnalysisOut)
async def seed_consent_decision(
    analysis_id: int,
    payload: SeedConsentDecisionIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """The user answered the results-page consent banner (their account-wide
    setting is "ask"). allow=True promotes this analysis now; allow=False just
    dismisses. ``remember`` ("yes"/"no") additionally updates the account setting.
    """
    result = await db.execute(
        select(UserAnalysis).where(UserAnalysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this analysis")

    analysis.pending_seed_consent = False
    # Minors can never opt in (their consent is locked to "no" at signup —
    # this guard is defense in depth in case of a stale token/state).
    minor = user.birth_year is not None and (datetime.utcnow().year - user.birth_year) < 18
    if payload.remember in ("yes", "no") and not minor:
        user.seed_consent = payload.remember
    await db.commit()
    await db.refresh(analysis)

    if payload.allow and not minor and analysis.promoted_seed_id is None:
        background_tasks.add_task(promote_analysis_to_seed, analysis.id, None, True)

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
    try:
        scores = json.loads(analysis.scores_json)
    except (ValueError, TypeError):
        scores = {}
    return {
        "id": analysis.id,
        "platform": analysis.platform or "tiktok",
        "filename": analysis.filename,
        "niche": analysis.niche,
        "caption": analysis.caption,
        "bio": analysis.bio,
        "scores_json": scores,
        "verdict": analysis.verdict,
        "actual_views": analysis.actual_views,
        "actual_likes": analysis.actual_likes,
        "video_url": analysis.video_url,
        "counts_fetched_at": analysis.counts_fetched_at,
        "pending_seed_consent": bool(analysis.pending_seed_consent),
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
