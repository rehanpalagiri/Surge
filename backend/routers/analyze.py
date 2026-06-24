import os
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update

from database import get_db, AsyncSessionLocal
from models import (
    AnalysisArtifact, OutcomeCollectionJob, OutcomeSnapshot, UsageEvent,
    User, UserAnalysis, UserProfile,
)
from schemas import (
    AnalysisOut, AnalysisSummaryOut, FeedbackIn, OutcomeSnapshotOut,
    SeedConsentDecisionIn, VideoLinkIn,
)
from services.gemini import analyze_video
from google.genai.errors import ClientError as _GeminiClientError
from services.niche_classifier import classify_niche, _match_canonical
from services.tiktok_fetch import fetch_tiktok, is_tiktok_url, download_tiktok_video
from services.instagram_fetch import fetch_instagram_likes, is_instagram_url
from services.rate_limit import get_rate_limit
from services.outcomes import (
    add_outcome_snapshot, post_id_from_url, schedule_outcome_jobs, sha256_file,
    upsert_artifact, utc_now_naive,
)
from services.throttle import check_rate
from auth import optional_user, require_user, is_minor
import services.r2 as r2

MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB
# Formats Gemini's File API accepts natively — no server-side transcoding needed.
# MKV (video/x-matroska) is the one common format Gemini does NOT support, so it
# stays excluded. Browsers report several MIME spellings per format, so include
# the common variants (e.g. AVI is usually reported as video/x-msvideo).
ALLOWED_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",                  # .mov
    "video/webm",
    "video/avi", "video/x-msvideo",     # .avi
    "video/mpeg", "video/mpg", "video/x-mpeg",  # .mpeg / .mpg
    "video/wmv", "video/x-ms-wmv",      # .wmv
    "video/x-flv",                      # .flv
    "video/3gpp",                       # .3gp
}
MAX_ACTUAL_VIEWS = 500_000_000  # sanity ceiling for feedback (no real video tops this)
REFRESH_COOLDOWN = timedelta(hours=24)  # min gap between video-link count refreshes

router = APIRouter(prefix="/api", tags=["analyze"])


def resolve_mode(user, has_usable_seeds: bool, channel_profile) -> str:
    """All new analyses use the same outcome-blind craft-review contract.

    Historical mode values remain readable, but prior AI opinions and
    likes/views-derived seed labels no longer change live craft assessments.
    """
    return "craft_review"


@router.post("/upload/presigned-url")
async def get_upload_presigned_url(
    filename: str = Form(...),
    content_type: str = Form(...),
):
    if not os.getenv("R2_ACCOUNT_ID"):
        raise HTTPException(status_code=503, detail="File upload service not configured.")
    ct = (content_type or "").lower()
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported video format. Try MP4, MOV, WEBM, AVI, WMV, MPEG, or 3GP (MKV isn't supported yet).")
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
    parent_id: Optional[int] = None,
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
        content_sha256 = sha256_file(file_path)

        # The live review is deliberately blind to prior outcomes, seed labels,
        # channel history, trends, and calibration notes.
        effective_mode = "craft_review"

        result = await analyze_video(
            file_path,
            canonical_niche,
            caption=caption,
            platform=platform,
            niche_raw=raw_niche,
            secondary_niche=secondary_niche or "",
            analysis_id=analysis_id,
        )

        async with AsyncSessionLocal() as db:
            row = (await db.execute(select(UserAnalysis).where(UserAnalysis.id == analysis_id))).scalar_one_or_none()
            if row:
                result["niche_needs_confirmation"] = niche_needs_confirmation
                row.scores_json = json.dumps(result)
                row.verdict = result.get("verdict", "Needs revision")
                row.mode = effective_mode
                row.status = "complete"
                row.calibration_version = 0
                await upsert_artifact(db, row.id, content_sha256=content_sha256)
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
    secondary: str = Form(""),  # user's optional 2nd niche pick (#6 blend) — advisory only
    caption: str = Form(""),
    bio: str = Form(""),
    platform: str = Form("tiktok"),
    project_name: str = Form(""),
    parent_id: str = Form(""),  # optional: ID of the analysis this updates
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
    # Real multi-niche: the secondary niche drives a promote-only weight merge in the
    # grading prompt (the PRIMARY still owns all rubric/seed/calibration lookups). It must
    # be canonical to key into NICHE_PROFILES — classify_niche already returns a canonical
    # secondary; an explicit pick is canonicalized here (no Gemini call). A custom/off-list
    # secondary that matches no canonical niche falls through and the merge simply no-ops.
    secondary_niche = niche_class.get("secondary")
    _explicit_secondary = (secondary or "").strip()[:80]
    if _explicit_secondary and _explicit_secondary.lower() != raw_niche.lower():
        secondary_niche = _match_canonical(_explicit_secondary) or _explicit_secondary
    # Rides along in scores_json (no schema change) so the frontend can prompt the
    # user to confirm/correct a niche Surge wasn't sure about (#4).
    niche_needs_confirmation = niche_class["needs_confirmation"]

    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    # Resolve parent_id — must belong to the current user (ownership check).
    resolved_parent_id: Optional[int] = None
    parent_analysis: Optional[UserAnalysis] = None
    if parent_id.strip().isdigit() and user:
        _pid = int(parent_id.strip())
        _parent = (await db.execute(
            select(UserAnalysis).where(UserAnalysis.id == _pid, UserAnalysis.user_id == user.id)
        )).scalar_one_or_none()
        if _parent:
            resolved_parent_id = _pid
            parent_analysis = _parent

    resolved_project_name = project_name.strip()[:80]
    if not resolved_project_name and parent_analysis and parent_analysis.project_name:
        resolved_project_name = parent_analysis.project_name
    if not resolved_project_name:
        resolved_project_name = "Untitled project"

    # --- R2 async path: file already in cloud storage, process in background ---
    if has_r2:
        analysis = UserAnalysis(
            user_id=user.id if user else None,
            platform=platform,
            filename=os.path.basename(r2_key),
            project_name=resolved_project_name,
            niche=raw_niche,  # the user's own words — shown in My Projects
            canonical_niche=canonical_niche,  # classifier label — calibration keys on this
            caption=caption or None,
            bio=bio or None,
            scores_json="{}",
            verdict="",
            mode="quick",
            status="pending",
            parent_id=resolved_parent_id,
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
            resolved_parent_id,
        )
        return {"id": analysis.id, "status": "pending"}

    if has_url and not has_file:
        url_stripped = video_url.strip()
        # Auto-detect platform from URL
        if "instagram.com" in url_stripped:
            raise HTTPException(
                status_code=400,
                detail="Instagram URL analysis is not yet supported. Please upload a video file instead.",
            )
        if not is_tiktok_url(url_stripped):
            raise HTTPException(
                status_code=400,
                detail="Only TikTok URLs are supported for direct link analysis. Please upload a video file instead.",
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
            raise HTTPException(status_code=400, detail="Unsupported video format. Try MP4, MOV, WEBM, AVI, WMV, MPEG, or 3GP (MKV isn't supported yet).")
        original_name = os.path.basename(file.filename or "upload")
        safe_name = f"{uuid.uuid4()}_{original_name}"
        file_path = os.path.join(uploads_dir, safe_name)
        content = await file.read()
        # Enforce size limit server-side (the 100MB UI check is bypassed by direct API calls)
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 100MB.")
        with open(file_path, "wb") as fh:
            fh.write(content)

    content_sha256 = sha256_file(file_path)

    # New reviews are intentionally blind to seed outcomes, creator history,
    # trends, and calibration data. Those legacy sources would confound a craft
    # critique with public performance.
    effective_mode = "craft_review"

    try:
        result = await analyze_video(
            file_path,
            canonical_niche,
            caption=caption,
            platform=platform,
            niche_raw=raw_niche,
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
        project_name=resolved_project_name,
        niche=raw_niche,  # the user's own words — shown in My Projects
        canonical_niche=canonical_niche,
        caption=caption or None,
        bio=bio or None,
        scores_json=json.dumps(result),
        verdict=result.get("verdict", "Needs revision"),
        mode=effective_mode,
        calibration_version=0,
        parent_id=resolved_parent_id,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    await upsert_artifact(db, analysis.id, content_sha256=content_sha256)
    await db.commit()

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


@router.get("/analyses/{analysis_id}/outcomes", response_model=list[OutcomeSnapshotOut])
async def analysis_outcomes(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    analysis = (await db.execute(
        select(UserAnalysis).where(UserAnalysis.id == analysis_id)
    )).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view these outcomes")
    return (await db.execute(
        select(OutcomeSnapshot)
        .where(OutcomeSnapshot.analysis_id == analysis_id)
        .order_by(OutcomeSnapshot.observed_at.asc(), OutcomeSnapshot.id.asc())
    )).scalars().all()


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
                "project_name": a.project_name,
                "niche": a.niche,
                "verdict": a.verdict,
                "caption_preview": caption_preview,
                "actual_views": a.actual_views,
                "actual_likes": a.actual_likes,
                "video_url": a.video_url,
                "counts_fetched_at": a.counts_fetched_at,
                "mode": a.mode or "quick",
                "parent_id": a.parent_id,
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Attach the user's posted video link to an analysis and auto-fetch its
    real stats. For TikTok: fetches views + likes via tikwm. For Instagram:
    fetches likes via RapidAPI (Instagram never exposes view counts).
    Call with url=None to refresh counts from the already-stored link
    (throttled to once per 24h).
    """
    result = await db.execute(
        select(UserAnalysis).where(UserAnalysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this analysis")

    is_ig = (analysis.platform or "tiktok") == "instagram"
    new_url = (payload.url or "").strip() or None
    if payload.post_age_hours is not None and payload.post_age_hours not in (24, 168, 720):
        raise HTTPException(status_code=400, detail="Capture age must be 24 hours, 7 days, or 30 days.")
    if analysis.video_url and new_url and new_url.rstrip("/") != analysis.video_url.rstrip("/"):
        raise HTTPException(
            status_code=409,
            detail="This experiment is already linked to a different post. Use a separate analysis for each post.",
        )
    # Supplying the same URL again is still a refresh; it must not bypass the
    # provider cooldown or create a burst of duplicate snapshots.
    if analysis.video_url and analysis.counts_fetched_at:
        elapsed = utc_now_naive() - analysis.counts_fetched_at
        if elapsed < REFRESH_COOLDOWN:
            raise HTTPException(
                status_code=429,
                detail="Stats were captured less than 24 hours ago — check back tomorrow.",
            )

    # ── Instagram branch ────────────────────────────────────────────────────
    if is_ig:
        if new_url and not is_instagram_url(new_url):
            raise HTTPException(
                status_code=400,
                detail="That doesn't look like an Instagram Reel link — paste the URL of your posted Reel.",
            )
        url = new_url or analysis.video_url
        if not url:
            raise HTTPException(status_code=400, detail="Paste the link to your posted Reel first.")

        try:
            likes = await fetch_instagram_likes(url)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Couldn't fetch that Reel: {e}")

        analysis.video_url = url
        analysis.actual_likes = likes
        analysis.counts_fetched_at = utc_now_naive()
        asserted_posted_at = (
            utc_now_naive() - timedelta(hours=payload.post_age_hours)
            if payload.post_age_hours in (24, 168, 720)
            else None
        )
        snapshot = add_outcome_snapshot(
            db,
            analysis_id=analysis.id,
            platform="instagram",
            source="rapidapi",
            views=None,
            likes=likes,
            posted_at=asserted_posted_at,
            integrity_flags_json=(
                json.dumps([
                    "third_party_metrics",
                    "paid_status_unknown",
                    "automated_activity_unknown",
                    "user_asserted_post_age",
                ])
                if asserted_posted_at else None
            ),
        )
        await upsert_artifact(
            db,
            analysis.id,
            platform_post_id=post_id_from_url(url, "instagram"),
        )
        await schedule_outcome_jobs(
            db,
            analysis_id=analysis.id,
            posted_at=asserted_posted_at,
            captured_horizon=snapshot.horizon,
        )
        await db.commit()
        await db.refresh(analysis)

        return _to_out(analysis)

    # ── TikTok branch ───────────────────────────────────────────────────────
    if new_url and not is_tiktok_url(new_url):
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like a TikTok link — paste the URL of your posted video.",
        )
    url = new_url or analysis.video_url
    if not url:
        raise HTTPException(status_code=400, detail="Paste the link to your posted TikTok first.")

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
    analysis.counts_fetched_at = utc_now_naive()
    snapshot = add_outcome_snapshot(
        db,
        analysis_id=analysis.id,
        platform="tiktok",
        source="tikwm",
        views=meta["view_count"],
        likes=meta["like_count"],
        posted_at=meta.get("posted_at"),
        comments=meta.get("comment_count"),
        shares=meta.get("share_count"),
        saves=meta.get("save_count"),
        creator_followers=meta.get("creator_followers"),
        provider_payload_hash=meta.get("provider_payload_hash"),
    )
    await upsert_artifact(
        db,
        analysis.id,
        platform_post_id=meta.get("video_id") or post_id_from_url(url, "tiktok"),
        creator_key=meta.get("author_handle"),
    )
    await schedule_outcome_jobs(
        db,
        analysis_id=analysis.id,
        posted_at=meta.get("posted_at"),
        captured_horizon=snapshot.horizon,
    )
    await db.commit()
    await db.refresh(analysis)

    return _to_out(analysis)


@router.post("/analyses/{analysis_id}/seed-consent", response_model=AnalysisOut)
async def seed_consent_decision(
    analysis_id: int,
    payload: SeedConsentDecisionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Record the user's research-retention choice for a legacy consent banner."""
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
    if feedback.post_age_hours is not None and feedback.post_age_hours not in (24, 168, 720):
        raise HTTPException(status_code=400, detail="Capture age must be 24 hours, 7 days, or 30 days.")

    if feedback.actual_views is not None:
        analysis.actual_views = feedback.actual_views
    if feedback.actual_likes is not None:
        analysis.actual_likes = feedback.actual_likes
    asserted_posted_at = (
        utc_now_naive() - timedelta(hours=feedback.post_age_hours)
        if feedback.post_age_hours in (24, 168, 720)
        else None
    )
    snapshot = add_outcome_snapshot(
        db,
        analysis_id=analysis.id,
        platform=analysis.platform or "tiktok",
        source="manual_unverified",
        views=feedback.actual_views,
        likes=feedback.actual_likes,
        posted_at=asserted_posted_at,
        integrity_flags_json=json.dumps(
            ["manual_unverified", "user_asserted_post_age"]
            if feedback.post_age_hours is not None else ["manual_unverified"]
        ),
    )
    if analysis.video_url:
        await schedule_outcome_jobs(
            db,
            analysis_id=analysis.id,
            posted_at=asserted_posted_at,
            captured_horizon=snapshot.horizon,
        )
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
    await db.execute(delete(UsageEvent).where(UsageEvent.analysis_id == analysis_id))
    await db.execute(delete(OutcomeCollectionJob).where(OutcomeCollectionJob.analysis_id == analysis_id))
    await db.execute(delete(OutcomeSnapshot).where(OutcomeSnapshot.analysis_id == analysis_id))
    await db.execute(delete(AnalysisArtifact).where(AnalysisArtifact.analysis_id == analysis_id))
    # Re-analysis children reference this row via parent_id (a self-FK). Detach
    # them first so the delete can't orphan a dangling reference or trip the FK
    # constraint on a fresh DB (where create_all built it). The child survives as
    # a standalone analysis the user can still open.
    await db.execute(
        update(UserAnalysis).where(UserAnalysis.parent_id == analysis_id).values(parent_id=None)
    )
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
        "project_name": analysis.project_name,
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
        "parent_id": analysis.parent_id,
        "created_at": analysis.created_at,
    }


def _to_locked(analysis: UserAnalysis) -> dict:
    """Anonymous view: the six craft dimension scores plus one issue. The
    per-dimension critique, recommended experiment, strengths, full improvement
    plan, and outcome timeline stay gated behind signup — guests see the numbers
    ("what"), not the qualitative detail ("why/how")."""
    try:
        scores = json.loads(analysis.scores_json)
    except (ValueError, TypeError):
        scores = {}
    plan = scores.get("improvement_plan") or []
    first_improvement = plan[0] if plan else None
    # Only the six numeric dimensions — never critique/experiment/plan/strengths.
    dimension_scores = {
        key: scores.get(key)
        for key in (
            "hook_velocity",
            "cut_frequency",
            "text_scannability",
            "curiosity_gap",
            "audio_visual_sync",
            "loop_seamlessness",
        )
    }
    return {
        "id": analysis.id,
        "platform": analysis.platform or "tiktok",
        "filename": analysis.filename,
        "project_name": analysis.project_name,
        "niche": analysis.niche,
        "caption": None,
        "bio": None,
        "scores_json": {
            **dimension_scores,
            "verdict": scores.get("verdict", analysis.verdict),
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
        "parent_id": analysis.parent_id,
        "created_at": analysis.created_at,
    }
