import os
import uuid
import json
import logging
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update

from database import get_db, AsyncSessionLocal
from models import (
    AnalysisArtifact, OutcomeCollectionJob, OutcomeSnapshot, PendingUpload,
    SeedVideo, UsageEvent, User, UserAnalysis, UserProfile,
)
from schemas import (
    AnalysisOut, AnalysisSummaryOut, ClaimAnalysisIn, FeedbackIn, OutcomeSnapshotOut,
    SeedConsentDecisionIn, VideoLinkIn,
)
from services.gemini import analyze_video
from services.seed_analysis import build_user_seed_analysis, score_outcome
from google.genai.errors import ClientError as _GeminiClientError
from services.niche_classifier import classify_niche, _match_canonical
from services.tiktok_fetch import fetch_tiktok, is_tiktok_url, download_tiktok_video
from services.instagram_fetch import fetch_instagram_likes, is_instagram_url
from services.rate_limit import get_rate_limit, MAX_BONUS
from services.craft_insights import build_craft_insights
from services.outcomes import (
    add_outcome_snapshot, post_id_from_url, schedule_outcome_jobs, sha256_file,
    upsert_artifact, utc_now_naive,
)
from services.throttle import check_rate, client_ip
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
# Caption/bio length caps. TikTok/Instagram captions top out ~2,200 chars; we cap
# server-side so a direct API caller can't send a megabyte of text and blow up the
# Gemini prompt (cost + latency + a prompt-injection surface). The UI also caps.
MAX_CAPTION_CHARS = 2_200
MAX_BIO_CHARS = 1_000
REFRESH_COOLDOWN = timedelta(hours=24)  # min gap between video-link count refreshes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analyze"])

# Presigned-upload ownership store — a shared DB table (pending_uploads) so a key
# issued by one worker is recognizable and consumable by ANY worker's /analyze call
# (was an in-memory dict, which is why WEB_CONCURRENCY was pinned to 1). Matches the
# 300s presign TTL; rows are pruned lazily on each access.
_PRESIGN_TTL = 300


async def _prune_pending(db: AsyncSession) -> None:
    """Delete presign rows older than the TTL. No commit — the caller commits it
    along with the record/pop it's about to do (or rolls this back harmlessly)."""
    cutoff = utc_now_naive() - timedelta(seconds=_PRESIGN_TTL)
    await db.execute(delete(PendingUpload).where(PendingUpload.issued_at < cutoff))


async def _record_pending(db: AsyncSession, r2_key: str, user_id: int | None, issuer_ip: str) -> None:
    """Persist a freshly issued upload key with its issuer identity, then commit so
    the key is immediately recognizable by any worker's /analyze call."""
    db.add(PendingUpload(r2_key=r2_key, user_id=user_id, issuer_ip=issuer_ip, issued_at=utc_now_naive()))
    await db.commit()


async def _pop_pending(db: AsyncSession, r2_key: str) -> Optional[tuple[int | None, str, datetime]]:
    """Atomically consume an upload key: SELECT … FOR UPDATE then DELETE so two
    concurrent /analyze calls (even on different workers) can't both claim the same
    key. Returns (user_id, issuer_ip, issued_at) or None if absent. Does NOT commit —
    the caller commits the delete together with the new analysis row, or rolls it
    back on an ownership mismatch so the key survives for a legitimate retry."""
    row = (await db.execute(
        select(PendingUpload).where(PendingUpload.r2_key == r2_key).with_for_update()
    )).scalar_one_or_none()
    if row is None:
        return None
    entry = (row.user_id, row.issuer_ip, row.issued_at)
    await db.execute(delete(PendingUpload).where(PendingUpload.r2_key == r2_key))
    return entry


def _limit_message(rl: dict) -> str:
    """Friendly 429 copy. Free users who hit the monthly cap are steered to CraftLint
    Pro (and the earn-by-linking bonus); a Pro user who trips the daily fair-use
    ceiling or the rolling cost-window cap gets a distinct message that never
    implies they should 'upgrade'."""
    if rl.get("tier") == "pro" and rl.get("limit_reason") == "fair_use":
        resets = ""
        if rl.get("fair_use_resets_at"):
            resets = f" It resets on {str(rl['fair_use_resets_at'])[:10]} (UTC)."
        return (
            f"You've reached today's fair-use limit of {rl.get('fair_use_daily_limit')} "
            f"analyses on CraftLint Pro.{resets} This keeps the service fast for everyone — "
            f"reach out if you routinely need a higher daily volume."
        )
    if rl.get("tier") == "pro" and rl.get("limit_reason") == "cost_window":
        hours = rl.get("cost_window_hours")
        budget = (rl.get("cost_window_budget_micros") or 0) / 1_000_000
        return (
            f"You've reached CraftLint Pro's rolling {hours}-hour spend limit "
            f"(${budget:.2f}). This resets gradually as usage from the last {hours} "
            f"hours ages out — try again shortly."
        )
    limit = rl.get("effective_limit")
    bonus_tip = (
        " Link a posted video to earn +1 analysis."
        if (rl.get("bonus") or 0) < MAX_BONUS else ""
    )
    resets = ""
    if rl.get("resets_at"):
        resets = f" Your free analyses reset on {str(rl['resets_at'])[:10]}."
    return (
        f"You've used all {limit} free analyses this month. "
        f"Upgrade to CraftLint Pro for unlimited analyses.{bonus_tip}{resets}"
    )


def _limit_headers(rl: dict) -> dict:
    """Advertise upgrade only to non-Pro users; a Pro fair-use block isn't an
    upsell opportunity."""
    return {} if rl.get("tier") == "pro" else {"X-Upgrade-Available": "1"}


def _title_from_caption(caption: str, max_words: int = 3) -> str:
    """Build a short project title from the first few words of the caption.

    Replaces the old dedicated project-name field — the caption now doubles as
    the project label. Returns "" when there's no usable caption (caller falls
    back to the parent title, then to a niche-based label in the UI)."""
    words = (caption or "").strip().split()
    return " ".join(words[:max_words])[:80]


def resolve_mode(user, has_usable_seeds: bool, channel_profile) -> str:
    """All new analyses use the same outcome-blind craft-review contract.

    Historical mode values remain readable, but prior AI opinions and
    likes/views-derived seed labels no longer change live craft assessments.
    """
    return "craft_review"


def _rubric_context(result: dict) -> dict:
    ctx = result.get("rubric_context") if isinstance(result, dict) else None
    return ctx if isinstance(ctx, dict) else {}


def _display_niche(raw_niche: str, result: dict, fallback: str) -> str:
    if (raw_niche or "").strip():
        return raw_niche
    ctx = _rubric_context(result)
    primary = ctx.get("reviewed_primary_niche") or ctx.get("primary_niche")
    secondary = ctx.get("reviewed_secondary_niche") or ctx.get("secondary_niche")
    if primary and primary != "Uncategorized":
        return f"{primary} + {secondary}" if secondary else str(primary)
    return fallback if fallback != "Uncategorized" else "Auto-detected"


def _canonical_from_result(result: dict, fallback: str) -> str:
    ctx = _rubric_context(result)
    primary = ctx.get("reviewed_primary_niche") or ctx.get("primary_niche")
    if primary and primary != "Uncategorized":
        return str(primary)
    return fallback


def _needs_niche_confirmation(result: dict, fallback: bool) -> bool:
    ctx = _rubric_context(result)
    confidence = str(ctx.get("confidence") or "").lower()
    source = str(ctx.get("source") or "")
    return bool(fallback or source == "fallback" or confidence == "low")


@router.post("/upload/presigned-url")
async def get_upload_presigned_url(
    request: Request,
    filename: str = Form(...),
    content_type: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(optional_user),
):
    requester_ip = client_ip(request)
    if user is None:
        if not await check_rate(db, f"guest-upload-url:{requester_ip}", 10, 24 * 3600):
            raise HTTPException(
                status_code=429,
                detail="Too many upload attempts. Sign up free to keep analyzing.",
            )
    else:
        rl = await get_rate_limit(user, db)
        if not rl["allowed"]:
            raise HTTPException(
                status_code=429,
                detail=_limit_message(rl),
                headers=_limit_headers(rl),
            )
    if not os.getenv("R2_ACCOUNT_ID"):
        raise HTTPException(status_code=503, detail="File upload service not configured.")
    ct = (content_type or "").lower()
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported video format. Try MP4, MOV, WEBM, AVI, WMV, MPEG, or 3GP (MKV isn't supported yet).")
    safe_filename = os.path.basename(filename or "upload")
    if len(safe_filename) > 140:
        safe_filename = safe_filename[-140:]
    key = f"uploads/{uuid.uuid4()}_{safe_filename}"
    upload_url = r2.presigned_upload_url(key, ct)
    await _prune_pending(db)
    await _record_pending(db, key, user.id if user else None, requester_ip)
    return {"upload_url": upload_url, "key": key}


async def _set_analysis_status(analysis_id: int, status: str) -> None:
    """Flip a background analysis to a lifecycle status (its own short session)."""
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(UserAnalysis).where(UserAnalysis.id == analysis_id))).scalar_one_or_none()
        if row:
            row.status = status
            await db.commit()


async def _mark_analysis_error(analysis_id: int, err_msg: str = "Analysis failed.") -> None:
    """Persist a background failure: store the error dict, flag status="error" so
    the row is excluded from the upload limiter and the UI shows a failure screen
    (never a credit-consuming all-zero scorecard)."""
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(UserAnalysis).where(UserAnalysis.id == analysis_id))).scalar_one_or_none()
        if row:
            row.scores_json = json.dumps({"error": err_msg})
            row.verdict = "Error"
            row.status = "error"
            await db.commit()


async def _finalize_analysis(
    analysis_id: int,
    file_path: str,
    raw_niche: str,
    canonical_niche: str,
    caption: str,
    platform: str,
    niche_needs_confirmation: bool = False,
    secondary_niche: Optional[str] = None,
    r2_key: Optional[str] = None,
) -> None:
    """Run the Gemini review for a file already on local disk, persist the result,
    and clean up. The single shared code path for "write the Gemini result and
    clean up" — used by both the R2 background path and the direct-upload
    background path. The live review is deliberately blind to prior individual
    outcomes, seed labels, channel history, and calibration notes. The one
    exception: when NICHE_SYNTHESIS_ENABLED is on, services.gemini.analyze_video
    injects the weekly, code-validated admin-seed niche/trend synthesis (never raw
    seed data, never per-video corrections) as prioritization context only — see
    services/niche_synthesis.py.

    Always removes the temp file (and the R2 object, when ``r2_key`` is given) in
    the finally, whether the review succeeded, failed, or raised.
    """
    try:
        content_sha256 = sha256_file(file_path)
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
                result["niche_needs_confirmation"] = _needs_niche_confirmation(result, niche_needs_confirmation)
                row.niche = _display_niche(raw_niche, result, canonical_niche)
                row.canonical_niche = _canonical_from_result(result, canonical_niche)
                row.scores_json = json.dumps(result)
                row.mode = "craft_review"
                row.calibration_version = 0
                # A non-429 Gemini failure returns an error dict (it doesn't raise),
                # so flag it "error" rather than storing an all-zero scorecard as a
                # successful, credit-consuming review.
                if result.get("error"):
                    row.verdict = "Error"
                    row.status = "error"
                else:
                    row.verdict = result.get("verdict", "Needs revision")
                    row.status = "complete"
                await upsert_artifact(db, row.id, content_sha256=content_sha256)
                await db.commit()

    except Exception as exc:
        # Log the real cause (status code + message) so prod can tell quota (429)
        # from auth/permission (403) from anything else — the stored message is
        # deliberately generic for users.
        logger.warning("Analysis %s failed: %r", analysis_id, exc)
        err_msg = (
            "We're at capacity right now — this didn't count against your limit. Give it a minute and try again."
            if isinstance(exc, _GeminiClientError) and exc.code in (429, 403)
            else "Analysis failed."
        )
        await _mark_analysis_error(analysis_id, err_msg)

    finally:
        try:
            os.remove(file_path)
        except OSError:
            pass
        if r2_key:
            try:
                await r2.delete(r2_key)
            except Exception:
                pass


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
    await _set_analysis_status(analysis_id, "processing")

    # Fetch the uploaded bytes from R2 to local disk. On any fetch failure, mark the
    # row "error" and clean up (temp file + R2 object) without reaching finalize.
    try:
        size = await r2.object_size(r2_key)
        if size is None:
            raise ValueError("Uploaded file is unavailable.")
        if size > MAX_FILE_BYTES:
            raise ValueError("File too large. Maximum size is 100MB.")
        video_bytes = await r2.download(r2_key)
        if len(video_bytes) > MAX_FILE_BYTES:
            raise ValueError("File too large. Maximum size is 100MB.")
        with open(file_path, "wb") as fh:
            fh.write(video_bytes)
    except Exception as exc:
        logger.warning("R2 fetch for analysis %s failed: %r", analysis_id, exc)
        await _mark_analysis_error(analysis_id)
        try:
            os.remove(file_path)
        except OSError:
            pass
        try:
            await r2.delete(r2_key)
        except Exception:
            pass
        return

    # File is on local disk — the shared finalize owns Gemini + persistence + cleanup
    # (it deletes both the temp file and the R2 object in its finally).
    await _finalize_analysis(
        analysis_id,
        file_path,
        raw_niche,
        canonical_niche,
        caption,
        platform,
        niche_needs_confirmation,
        secondary_niche,
        r2_key=r2_key,
    )


async def _run_local_analysis(
    analysis_id: int,
    file_path: str,
    raw_niche: str,
    canonical_niche: str,
    caption: str,
    platform: str,
    niche_needs_confirmation: bool = False,
    secondary_niche: Optional[str] = None,
) -> None:
    """Background finalize for the direct upload / TikTok-URL path. The file is
    already on local disk (the request handler streamed it there), so this skips
    the R2 fetch step and goes straight to the shared finalize."""
    await _set_analysis_status(analysis_id, "processing")
    await _finalize_analysis(
        analysis_id,
        file_path,
        raw_niche,
        canonical_niche,
        caption,
        platform,
        niche_needs_confirmation,
        secondary_niche,
    )


@router.get("/analyses/{analysis_id}/status")
async def analysis_status(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(optional_user),
):
    result = await db.execute(
        select(
            UserAnalysis.id, UserAnalysis.status, UserAnalysis.user_id, UserAnalysis.scores_json
        ).where(UserAnalysis.id == analysis_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    # Visibility mirrors GET /analyses/{id}: the owner, or anyone while the analysis
    # is still an unclaimed guest row (so the guest results page can poll its own
    # in-flight upload). A logged-in stranger polling someone else's claimed
    # analysis gets 404 — no cross-tenant status/existence oracle over sequential IDs.
    if row.user_id is not None and (user is None or row.user_id != user.id):
        raise HTTPException(status_code=404, detail="Analysis not found")
    status = row.status or "complete"
    out = {"id": row.id, "status": status}
    if status == "error":
        # Surface the real reason (e.g. "we're at capacity") instead of leaving the
        # caller to show a generic failure for both a quota hit and a real bug.
        try:
            out["message"] = json.loads(row.scores_json or "{}").get("error")
        except (json.JSONDecodeError, AttributeError):
            pass
    return out


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
    # Cap untrusted free-text inputs before they reach storage or the Gemini prompt.
    caption = (caption or "")[:MAX_CAPTION_CHARS]
    bio = (bio or "")[:MAX_BIO_CHARS]

    has_file = bool(file and file.filename)
    has_url = bool(video_url.strip())
    has_r2 = bool(r2_key.strip())
    if not has_file and not has_url and not has_r2:
        raise HTTPException(status_code=400, detail="Provide a video file or a TikTok URL.")

    # Rate limits first — before any Gemini calls so we don't burn API quota
    # on requests we're going to reject anyway.
    if user is None:
        ip = client_ip(request)
        if not await check_rate(db, f"guest:{ip}", 5, 24 * 3600):
            raise HTTPException(
                status_code=429,
                detail="You've used your 5 free analyses. Sign up free to keep analyzing.",
            )

    # Rate limit authenticated users: free = 3 analyses/month, Pro = unlimited.
    if user:
        rl = await get_rate_limit(user, db)
        if not rl["allowed"]:
            raise HTTPException(
                status_code=429,
                detail=_limit_message(rl),
                headers=_limit_headers(rl),
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
    # user to confirm/correct a niche CraftLint wasn't sure about (#4).
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

    # Project title: no dedicated name field anymore — derive it from the first
    # few words of the caption. Falls back to the parent's title (re-analyses);
    # if still empty it stays None and the UI labels it "{niche} project".
    resolved_project_name = project_name.strip()[:80] or _title_from_caption(caption)
    if not resolved_project_name and parent_analysis and parent_analysis.project_name:
        resolved_project_name = parent_analysis.project_name
    resolved_project_name = resolved_project_name or None

    # --- R2 async path: file already in cloud storage, process in background ---
    if has_r2:
        await _prune_pending(db)
        _upload_entry = await _pop_pending(db, r2_key.strip())
        if _upload_entry is None:
            raise HTTPException(
                status_code=400,
                detail="Upload key not recognized or expired. Please re-upload your video.",
            )
        _issued_user_id, _issued_ip, _ = _upload_entry
        _caller_user_id = user.id if user else None
        _caller_ip = client_ip(request)
        if _issued_user_id != _caller_user_id or (
            _caller_user_id is None and _issued_ip != _caller_ip
        ):
            raise HTTPException(
                status_code=403,
                detail="Upload key does not belong to this session.",
            )
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
            guest_claim_token=secrets.token_urlsafe(32) if user is None else None,
        )
        db.add(analysis)
        await db.commit()
        # analysis.id is populated by the flush the commit performed; the row is
        # now durable so the background task's separate session can read it. No
        # refresh needed — the response only echoes id + status.
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
        out = {"id": analysis.id, "status": "pending"}
        if analysis.guest_claim_token:
            out["claim_token"] = analysis.guest_claim_token
        return out

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
            caption = (auto_caption or "")[:MAX_CAPTION_CHARS]
        # The caption may only now be available (auto-pulled from the TikTok URL),
        # so derive the title from it if we still don't have one.
        if not resolved_project_name:
            resolved_project_name = _title_from_caption(caption) or None
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
        # Stream to disk in bounded chunks and abort the moment the running total
        # crosses the cap. Reading the whole body into one bytes object first (the
        # old approach) let a direct API caller push a multi-GB upload and OOM the
        # single worker — the size check only ran AFTER the allocation. Now peak
        # memory is one chunk regardless of how large a body is sent.
        size = 0
        try:
            with open(file_path, "wb") as fh:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise HTTPException(status_code=413, detail="File too large. Maximum size is 100MB.")
                    fh.write(chunk)
        except HTTPException:
            try:
                os.remove(file_path)
            except OSError:
                pass
            raise

    # Create the row as "pending" and commit immediately, then background the work
    # — mirroring the R2 path. This releases the pooled DB connection and its open
    # transaction BEFORE the 30–90s Gemini upload + poll + two passes, so a burst of
    # concurrent direct analyses no longer holds connections across an external call
    # and starves the pool (every other DB route was queuing behind them).
    #
    # Behavior change (intended, matches the R2 path): a Gemini 429/403 now surfaces
    # as a background status="error" the results page shows — no credit charged —
    # instead of the old inline 503, since the caller already has {"status":"pending"}.
    analysis = UserAnalysis(
        user_id=user.id if user else None,
        platform=platform,
        filename=safe_name,
        project_name=resolved_project_name,
        niche=raw_niche,
        canonical_niche=canonical_niche,
        caption=caption or None,
        bio=bio or None,
        scores_json="{}",
        verdict="",
        mode="craft_review",
        calibration_version=0,
        status="pending",
        parent_id=resolved_parent_id,
        guest_claim_token=secrets.token_urlsafe(32) if user is None else None,
    )
    db.add(analysis)
    await db.commit()
    # analysis.id is populated by the flush the commit performed; the row is durable
    # so the background task's separate session can read it (expire_on_commit=False
    # keeps id/guest_claim_token readable here without a refresh).
    background_tasks.add_task(
        _run_local_analysis,
        analysis.id,
        file_path,
        raw_niche,
        canonical_niche,
        caption,
        platform,
        niche_needs_confirmation,
        secondary_niche,
    )
    out = {"id": analysis.id, "status": "pending"}
    if analysis.guest_claim_token:
        out["claim_token"] = analysis.guest_claim_token
    return out


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
    return await get_rate_limit(user, db)


@router.get("/me/craft-insights")
async def my_craft_insights(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    """Craft assessments grounded against the creator's OWN verified outcomes.

    Descriptive only — observed like rate at a single maturity window, with
    explicit sample sizes. Never a causal claim or a pixel-based forecast.
    """
    return await build_craft_insights(user.id, db)


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
    payload: Optional[ClaimAnalysisIn] = Body(None),
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
        supplied = (payload.claim_token if payload else None) or ""
        stored = analysis.guest_claim_token or ""
        if not stored or not supplied or not hmac.compare_digest(supplied, stored):
            raise HTTPException(status_code=403, detail="This analysis can only be claimed from the browser that created it.")
        analysis.user_id = user.id
        analysis.guest_claim_token = None
        await db.commit()
        await db.refresh(analysis)
    elif analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="This analysis belongs to another account")
    return _to_out(analysis)


def _normalize_handle(h: str) -> str:
    return (h or "").strip().lstrip("@").lower()


async def _sync_user_seed(db: AsyncSession, analysis: UserAnalysis, user: User) -> None:
    """Introduce (or refresh) a creator's upload in the shared seed pool once it has
    VERIFIED provider counts.

    A "user seed" reuses the analysis's counts-blind craft review as its
    ``gemini_analysis`` and derives its rating deterministically from the real counts
    via ``score_outcome()`` — the same craft-blind / code-rated split the admin and
    harvest seed pipelines use. This is the higher-quality signal (a real outcome, not
    a curator's guess) and is what starts populating the Instagram seed pool, which is
    otherwise empty.

    Guarantees:
      • Only VERIFIED provider fetches reach here (called from ``link_video`` after a
        successful tikwm / RapidAPI fetch). Manual/unverified counts never promote.
      • Never for minors (their ``seed_consent`` is locked "no" at signup), and skipped
        when the creator has explicitly opted out (``seed_consent == "no"``).
      • Idempotent: the analysis's ``promoted_seed_id`` links to its one seed row, so a
        later refresh updates that row in place instead of creating duplicates.
      • Errored/incomplete reviews are never seeded.
    """
    if is_minor(user) or (user.seed_consent == "no"):
        return
    likes = analysis.actual_likes
    if likes is None or (analysis.status not in (None, "complete")):
        return
    try:
        review = json.loads(analysis.scores_json) if analysis.scores_json else {}
    except (ValueError, TypeError):
        return
    if not isinstance(review, dict) or review.get("error"):
        return

    views = analysis.actual_views
    platform = analysis.platform or "tiktok"
    niche = analysis.canonical_niche or "Uncategorized"
    rating, driver, driver_conf = score_outcome(views, likes)
    blob = build_user_seed_analysis(review, driver, driver_conf)

    seed = None
    if analysis.promoted_seed_id:
        seed = (await db.execute(
            select(SeedVideo).where(SeedVideo.id == analysis.promoted_seed_id)
        )).scalar_one_or_none()
    if seed is None:
        seed = SeedVideo(
            filename=analysis.filename,
            source="user",
            platform=platform,
            niche=niche,
            like_count=likes,
        )
        db.add(seed)
        await db.flush()  # assign seed.id before linking it back
        analysis.promoted_seed_id = seed.id

    seed.platform = platform
    seed.niche = niche
    seed.view_count = views
    seed.like_count = likes
    seed.rating = rating
    seed.gemini_analysis = json.dumps(blob)
    seed.posted_at = analysis.counts_fetched_at


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
    # Block URL changes only once stats have been confirmed (counts_fetched_at set).
    # An unconfirmed link (URL saved but stats never fetched due to provider outage)
    # can be corrected by re-submitting.
    if (analysis.video_url and analysis.counts_fetched_at and
            new_url and new_url.rstrip("/") != analysis.video_url.rstrip("/")):
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
            # Both providers down — save the URL so the link is recorded.
            logger.warning("fetch_instagram_likes for analysis %s failed: %r — saving URL without stats", analysis_id, e)
            if not analysis.video_url:
                analysis.video_url = url
                await db.commit()
                await db.refresh(analysis)
            return _to_out(analysis)

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
        await _sync_user_seed(db, analysis, user)
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
        # Provider temporarily down — save the URL so the link is recorded.
        # Stats will be null until the user retries with the refresh button.
        logger.warning("fetch_tiktok for analysis %s failed: %r — saving URL without stats", analysis_id, e)
        if not analysis.video_url:
            analysis.video_url = url
            await db.commit()
            await db.refresh(analysis)
        return _to_out(analysis)

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
    await _sync_user_seed(db, analysis, user)
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
    manual_url = (feedback.video_url or "").strip() or None
    if manual_url:
        platform = analysis.platform or "tiktok"
        valid = is_instagram_url(manual_url) if platform == "instagram" else is_tiktok_url(manual_url)
        if not valid:
            label = "Instagram Reel" if platform == "instagram" else "TikTok"
            raise HTTPException(status_code=400, detail=f"That doesn't look like a {label} link.")
        if analysis.video_url and manual_url.rstrip("/") != analysis.video_url.rstrip("/"):
            raise HTTPException(
                status_code=409,
                detail="This experiment is already linked to a different post. Use a separate analysis for each post.",
            )
        analysis.video_url = manual_url

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


def _to_out(analysis: UserAnalysis, *, include_claim_token: bool = False) -> dict:
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
        "claim_token": analysis.guest_claim_token if include_claim_token and analysis.user_id is None else None,
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
            # Surface failures even in the locked/guest view so a guest whose
            # analysis errored sees the "Analysis failed" screen instead of a
            # locked card showing 0/10 across every dimension.
            **({"error": scores["error"]} if scores.get("error") else {}),
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
