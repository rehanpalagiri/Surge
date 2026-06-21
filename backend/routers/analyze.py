import os
import uuid
import json
from datetime import datetime, timedelta
from statistics import median
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db, AsyncSessionLocal
from models import SeedVideo, UserAnalysis, UserProfile, User, NicheInsight, TrendSummary, CalibrationNote
from schemas import AnalysisOut, FeedbackIn, AnalysisSummaryOut, VideoLinkIn, SeedConsentDecisionIn
from services.gemini import analyze_video, select_seed_examples
from services.calibration import load_calibration_note
from google.genai.errors import ClientError as _GeminiClientError
from services.channel_profile import build_channel_profile
from services.niche_classifier import classify_niche
from services.tiktok_fetch import fetch_tiktok, is_tiktok_url, download_tiktok_video
from services.seed_promote import promote_analysis_to_seed
from services.seed_correction import audit_prediction
from services.rate_limit import get_rate_limit
from services.throttle import check_rate
from auth import optional_user, require_user, is_minor
import services.r2 as r2

MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB
ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime"}
MAX_ACTUAL_VIEWS = 500_000_000  # sanity ceiling for feedback (no real video tops this)
REFRESH_COOLDOWN = timedelta(hours=24)  # min gap between video-link count refreshes

router = APIRouter(prefix="/api", tags=["analyze"])


def resolve_mode(user, has_usable_seeds: bool, channel_profile) -> str:
    """Auto-escalate to the best mode available — users never choose.
    Guests always get Quick. Auth users get the best mode the data supports:
      Deep  → needs a channel profile (>= 2 prior analyses)
      Thinking → needs usable seed buckets
      Quick → fallback when no enrichment data exists yet
    """
    if user is None:
        return "quick"
    if channel_profile:
        return "deep_thinking"
    if has_usable_seeds:
        return "thinking"
    return "quick"


@router.post("/upload/presigned-url")
async def get_upload_presigned_url(
    filename: str = Form(...),
    content_type: str = Form(...),
):
    if not os.getenv("R2_ACCOUNT_ID"):
        raise HTTPException(status_code=503, detail="File upload service not configured.")
    ct = (content_type or "").lower()
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only MP4 and MOV video files are supported.")
    key = f"uploads/{uuid.uuid4()}_{os.path.basename(filename or 'upload')}"
    upload_url = r2.presigned_upload_url(key, ct)
    return {"upload_url": upload_url, "key": key}


async def _run_r2_analysis(
    analysis_id: int,
    r2_key: str,
    uploads_dir: str,
    user_id: Optional[int],
    raw_niche: str,
    canonical_niche: str,
    caption: str,
    bio: str,
    platform: str,
    niche_needs_confirmation: bool = False,
    secondary_niche: Optional[str] = None,
) -> None:
    file_path = os.path.join(uploads_dir, f"{uuid.uuid4()}_r2upload.mp4")
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(UserAnalysis).where(UserAnalysis.id == analysis_id))).scalar_one_or_none()
        if row:
            row.status = "processing"
            await db.commit()

    try:
        video_bytes = await r2.download(r2_key)
        with open(file_path, "wb") as fh:
            fh.write(video_bytes)

        # Re-query context with a fresh session so we get up-to-date data.
        async with AsyncSessionLocal() as db:
            user = None
            if user_id is not None:
                user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

            high_seeds: list = []
            low_seeds: list = []
            niche_insight: str | None = None
            trend_context: str | None = None
            calibration_note: dict | None = None
            if user:
                from datetime import timezone
                insight_row = (await db.execute(
                    select(NicheInsight).where(
                        NicheInsight.platform == platform,
                        NicheInsight.niche == canonical_niche,
                    )
                )).scalar_one_or_none()
                if insight_row and (insight_row.insight or "").strip():
                    niche_insight = insight_row.insight
                else:
                    seeds = (await db.execute(select(SeedVideo).where(SeedVideo.platform == platform))).scalars().all()
                    high_seeds, low_seeds = select_seed_examples(seeds, canonical_niche)

                trend_row = (await db.execute(
                    select(TrendSummary).where(
                        TrendSummary.platform == platform,
                        TrendSummary.niche == canonical_niche,
                    )
                )).scalar_one_or_none()
                if trend_row and (trend_row.trend_text or "").strip():
                    ref = trend_row.generated_at
                    if ref.tzinfo is None:
                        ref = ref.replace(tzinfo=timezone.utc)
                    if ref >= datetime.now(timezone.utc) - timedelta(days=7):
                        trend_context = trend_row.trend_text

                # Build #3: calibration nudge (applied only in Thinking/Deep + when
                # high-confidence — gemini.analyze_video makes the final call).
                calibration_note = await load_calibration_note(db, platform, canonical_niche)

            has_usable_seeds = bool(niche_insight or high_seeds or low_seeds)

            channel_profile = None
            if user:
                hist = (await db.execute(
                    select(UserAnalysis).where(
                        UserAnalysis.user_id == user.id,
                        UserAnalysis.platform == platform,
                    )
                )).scalars().all()
                channel_profile = build_channel_profile(hist)

            effective_mode = resolve_mode(user, has_usable_seeds, channel_profile)

            creator_like_baseline: dict | None = None
            if user:
                past_likes = [
                    r for r in (await db.execute(
                        select(UserAnalysis.actual_likes).where(
                            UserAnalysis.user_id == user.id,
                            UserAnalysis.platform == platform,
                            UserAnalysis.actual_likes.is_not(None),
                        ).order_by(UserAnalysis.created_at.desc()).limit(10)
                    )).scalars().all()
                    if r is not None and r >= 0
                ]
                if len(past_likes) >= 2:
                    med = int(median(past_likes))
                    creator_like_baseline = {
                        "median_likes": med,
                        "sample_count": len(past_likes),
                        "min_likes": min(past_likes),
                        "max_likes": max(past_likes),
                    }

            profile_context = ""
            if user and effective_mode in ("thinking", "deep_thinking"):
                prof = (await db.execute(
                    select(UserProfile).where(
                        UserProfile.user_id == user.id,
                        UserProfile.platform == platform,
                    )
                )).scalar_one_or_none()
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

        seeds_high = high_seeds if effective_mode in ("thinking", "deep_thinking") else []
        seeds_low = low_seeds if effective_mode in ("thinking", "deep_thinking") else []
        profile_arg = channel_profile if effective_mode == "deep_thinking" else None

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
            niche_insight=niche_insight if effective_mode in ("thinking", "deep_thinking") else None,
            trend_context=trend_context if effective_mode in ("thinking", "deep_thinking") else None,
            calibration_note=calibration_note if effective_mode in ("thinking", "deep_thinking") else None,
            secondary_niche=secondary_niche or "",
        )

        async with AsyncSessionLocal() as db:
            row = (await db.execute(select(UserAnalysis).where(UserAnalysis.id == analysis_id))).scalar_one_or_none()
            if row:
                result["niche_needs_confirmation"] = niche_needs_confirmation
                row.scores_json = json.dumps(result)
                row.verdict = result.get("verdict", "Needs work")
                row.mode = effective_mode
                row.status = "complete"
                # Build #3: record which calibration version nudged this prediction
                # (0 / absent = un-nudged) so audit_prediction can exclude it later.
                row.calibration_version = int(result.get("calibration_version") or 0)
                await db.commit()

    except Exception as exc:
        err_msg = "AI analysis is temporarily unavailable." if isinstance(exc, _GeminiClientError) and exc.code in (429, 403) else "Analysis failed."
        async with AsyncSessionLocal() as db:
            row = (await db.execute(select(UserAnalysis).where(UserAnalysis.id == analysis_id))).scalar_one_or_none()
            if row:
                row.scores_json = json.dumps({"error": err_msg})
                row.verdict = "Error"
                row.status = "error"
                await db.commit()

    finally:
        try:
            os.remove(file_path)
        except OSError:
            pass
        try:
            await r2.delete(r2_key)
        except Exception:
            pass


@router.get("/analyses/{analysis_id}/status")
async def analysis_status(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserAnalysis.id, UserAnalysis.status).where(UserAnalysis.id == analysis_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"id": row.id, "status": row.status or "complete"}


@router.post("/analyze")
async def analyze(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    video_url: str = Form(""),
    r2_key: str = Form(""),
    niche: str = Form(""),
    caption: str = Form(""),
    bio: str = Form(""),
    platform: str = Form("tiktok"),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(optional_user),
):
    platform = platform.lower() if platform.lower() in ("tiktok", "instagram") else "tiktok"

    has_file = bool(file and file.filename)
    has_url = bool(video_url.strip())
    has_r2 = bool(r2_key.strip())
    if not has_file and not has_url and not has_r2:
        raise HTTPException(status_code=400, detail="Provide a video file or a TikTok URL.")

    # Rate limits first — before any Gemini calls so we don't burn API quota
    # on requests we're going to reject anyway.
    if user is None:
        ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        if not check_rate(f"guest:{ip}", 5, 24 * 3600):
            raise HTTPException(
                status_code=429,
                detail="You've used your 5 free analyses. Sign up free to get 10 analyses every 3 hours.",
            )

    # Rate limit authenticated users (DB-backed, resets on a rolling window)
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

    # Niche: optional — empty input classifies to Uncategorized (generic rubric),
    # never a silent default. classify_niche("") returns the Uncategorized sentinel.
    raw_niche = niche.strip()[:200]
    niche_class = await classify_niche(raw_niche)
    canonical_niche = niche_class["canonical"]
    # Advisory secondary niche (#6 Light blend) — passed to the grading prompt only;
    # it does NOT change rubric/seed/weight lookups (those stay on the primary).
    secondary_niche = niche_class.get("secondary")
    # Rides along in scores_json (no schema change) so the frontend can prompt the
    # user to confirm/correct a niche Surge wasn't sure about (#4).
    niche_needs_confirmation = niche_class["needs_confirmation"]

    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    # --- R2 async path: file already in cloud storage, process in background ---
    if has_r2:
        analysis = UserAnalysis(
            user_id=user.id if user else None,
            platform=platform,
            filename=os.path.basename(r2_key),
            niche=raw_niche,  # the user's own words — shown in My Projects
            canonical_niche=canonical_niche,  # classifier label — calibration keys on this
            caption=caption or None,
            bio=bio or None,
            scores_json="{}",
            verdict="",
            mode="quick",
            status="pending",
        )
        db.add(analysis)
        await db.commit()
        await db.refresh(analysis)
        background_tasks.add_task(
            _run_r2_analysis,
            analysis.id,
            r2_key.strip(),
            uploads_dir,
            user.id if user else None,
            raw_niche,
            canonical_niche,
            caption,
            bio,
            platform,
            niche_needs_confirmation,
            secondary_niche,
        )
        return {"id": analysis.id, "status": "pending"}

    if has_url and not has_file:
        url_stripped = video_url.strip()
        # Auto-detect platform from URL
        if "instagram.com" in url_stripped:
            raise HTTPException(
                status_code=400,
                detail="Instagram URL analysis is not yet supported. Please upload an MP4 file.",
            )
        if not is_tiktok_url(url_stripped):
            raise HTTPException(
                status_code=400,
                detail="Only TikTok URLs are supported for direct link analysis. Please upload an MP4 or .MOV file.",
            )
        platform = "tiktok"
        try:
            video_bytes, auto_caption = await download_tiktok_video(url_stripped)
        except (ValueError, Exception) as exc:
            raise HTTPException(status_code=400, detail=f"Could not fetch TikTok video: {exc}")
        if not caption and auto_caption:
            caption = auto_caption
        safe_name = f"{uuid.uuid4()}_tiktok.mp4"
        file_path = os.path.join(uploads_dir, safe_name)
        with open(file_path, "wb") as fh:
            fh.write(video_bytes)
    else:
        # File upload path
        if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="Only MP4 and MOV video files are supported.")
        original_name = os.path.basename(file.filename or "upload")
        safe_name = f"{uuid.uuid4()}_{original_name}"
        file_path = os.path.join(uploads_dir, safe_name)
        content = await file.read()
        # Enforce size limit server-side (the 100MB UI check is bypassed by direct API calls)
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 100MB.")
        with open(file_path, "wb") as fh:
            fh.write(content)

    # --- Niche intelligence + seed reference (auth users always get enrichment) ---
    high_seeds: list = []
    low_seeds: list = []
    niche_insight: str | None = None
    trend_context: str | None = None
    calibration_note: dict | None = None
    if user:
        # Prefer the synthesized niche insight block; fall back to raw seed lists.
        insight_result = await db.execute(
            select(NicheInsight).where(
                NicheInsight.platform == platform,
                NicheInsight.niche == canonical_niche,
            )
        )
        insight_row = insight_result.scalar_one_or_none()
        if insight_row and (insight_row.insight or "").strip():
            niche_insight = insight_row.insight
        else:
            seeds_result = await db.execute(
                select(SeedVideo).where(SeedVideo.platform == platform)
            )
            seeds = seeds_result.scalars().all()
            high_seeds, low_seeds = select_seed_examples(seeds, canonical_niche)

        # Trend intelligence: inject if generated within the last 7 days.
        from datetime import timezone
        trend_result = await db.execute(
            select(TrendSummary).where(
                TrendSummary.platform == platform,
                TrendSummary.niche == canonical_niche,
            )
        )
        trend_row = trend_result.scalar_one_or_none()
        if trend_row and (trend_row.trend_text or "").strip():
            ref = trend_row.generated_at
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            if ref >= datetime.now(timezone.utc) - timedelta(days=7):
                trend_context = trend_row.trend_text

        # Build #3: calibration nudge (applied only in Thinking/Deep + when
        # high-confidence — gemini.analyze_video makes the final call).
        calibration_note = await load_calibration_note(db, platform, canonical_niche)

    has_usable_seeds = bool(niche_insight or high_seeds or low_seeds)

    # --- Creator channel profile (needs >= 2 prior analyses — always attempt for auth users) ---
    channel_profile = None
    if user:
        hist_result = await db.execute(
            select(UserAnalysis).where(
                UserAnalysis.user_id == user.id,
                UserAnalysis.platform == platform,
            )
        )
        channel_profile = build_channel_profile(hist_result.scalars().all())

    effective_mode = resolve_mode(user, has_usable_seeds, channel_profile)

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
            niche_insight=niche_insight if effective_mode in ("thinking", "deep_thinking") else None,
            trend_context=trend_context if effective_mode in ("thinking", "deep_thinking") else None,
            calibration_note=calibration_note if effective_mode in ("thinking", "deep_thinking") else None,
            secondary_niche=secondary_niche or "",
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

    result["niche_needs_confirmation"] = niche_needs_confirmation
    analysis = UserAnalysis(
        user_id=user.id if user else None,
        platform=platform,
        filename=safe_name,
        niche=raw_niche,  # the user's own words — shown in My Projects
        canonical_niche=canonical_niche,  # classifier label — calibration keys on this
        caption=caption or None,
        bio=bio or None,
        scores_json=json.dumps(result),
        verdict=result.get("verdict", "Needs work"),
        mode=effective_mode,
        # Build #3: 0 / absent = un-nudged (the safe default).
        calibration_version=int(result.get("calibration_version") or 0),
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
    # Full view ONLY for the authenticated owner. Everyone else — anonymous users,
    # non-owners, AND unclaimed analyses (user_id is None) — gets the locked teaser.
    # An unclaimed analysis is unlocked by its creator via /claim (which sets user_id),
    # never by a stranger guessing sequential IDs. (Without the `user_id is None` guard,
    # any logged-in user could read any guest's full analysis — an IDOR + paywall bypass.)
    if user is None or analysis.user_id is None or analysis.user_id != user.id:
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

    # Audit prediction accuracy against real outcome — independent of promotion gate.
    background_tasks.add_task(audit_prediction, analysis.id)

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
    minor = is_minor(user)
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
    if feedback.actual_views is not None:
        if feedback.actual_views < 0:
            raise HTTPException(status_code=400, detail="Views can't be negative.")
        if feedback.actual_views > MAX_ACTUAL_VIEWS:
            raise HTTPException(status_code=400, detail="That view count is too high to be real.")
    if feedback.actual_likes is not None:
        if feedback.actual_likes < 0:
            raise HTTPException(status_code=400, detail="Likes can't be negative.")
        # Only compare likes vs views when both are supplied (not meaningful for Instagram).
        if feedback.actual_views is not None and feedback.actual_likes > feedback.actual_views:
            raise HTTPException(status_code=400, detail="Likes can't exceed views.")

    if feedback.actual_views is not None:
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
        "niche_needs_confirmation": bool(scores.get("niche_needs_confirmation")),
        "mode": analysis.mode or "quick",
        "created_at": analysis.created_at,
    }


def _to_locked(analysis: UserAnalysis) -> dict:
    """Anonymous (free-tier) view: overall score, verdict, and the single highest-priority
    improvement are exposed as a teaser. Full plan, rewrites, and all detail are locked."""
    try:
        scores = json.loads(analysis.scores_json)
    except (ValueError, TypeError):
        scores = {}
    plan = scores.get("improvement_plan") or []
    first_improvement = plan[0] if plan else None
    return {
        "id": analysis.id,
        "platform": analysis.platform or "tiktok",
        "filename": analysis.filename,
        "niche": analysis.niche,
        "caption": None,
        "bio": None,
        "scores_json": {
            "verdict": scores.get("verdict", analysis.verdict),
            "overall_score": scores.get("overall_score"),
            "first_improvement": first_improvement,
            "locked": True,
        },
        "verdict": analysis.verdict,
        "actual_views": None,
        "actual_likes": None,
        "video_url": None,
        "counts_fetched_at": None,
        "pending_seed_consent": False,
        "mode": analysis.mode or "quick",
        "created_at": analysis.created_at,
    }
