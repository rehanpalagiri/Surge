import os
import json
import uuid
import hmac
from datetime import datetime, timedelta
from services.clock import utc_now_naive
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func, case

from database import get_db
from models import SeedVideo, FetchStatus, NicheInsight, TrendSummary, CalibrationNote, UsageEvent, UserAnalysis
from schemas import SeedVideoOut
from services.seed_analysis import analyze_seed_video
from services.seed_insights import generate_niche_insight
from services.calibration import generate_calibration_note, GLOBAL_NICHE
from services.tiktok_fetch import fetch_tiktok
from services.seed_harvest import harvest_all, get_last_harvest, NICHE_KEYWORDS
from services.instagram_harvest import harvest_instagram_all, get_last_instagram_harvest
from services.trend_harvest import harvest_trending, get_last_trend_harvest
from services.trend_insights import generate_trend_insight
from services.outcome_collection import collect_due_outcomes, collection_status, collector_health
from services.economics import build_operations_report
from services.telemetry import gemini_price_source

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def check_admin(x_admin_password: Optional[str] = Header(None)):
    expected = os.getenv("ADMIN_PASSWORD", "viraliq-admin")
    if not x_admin_password or not hmac.compare_digest(x_admin_password, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing admin password")


class CollectDueRequest(BaseModel):
    # Daily batch size. The external scheduler (collect-outcomes.yml) and the
    # in-process APScheduler both intend a full batch; the service clamps to 100.
    limit: int = 100


@router.post("/outcomes/collect-due")
async def collect_due_outcome_jobs(
    req: CollectDueRequest = CollectDueRequest(),
    _: None = Depends(check_admin),
):
    """Run due maturity jobs. Intended for a trusted external scheduler.

    ``limit`` is read from the JSON body so the GitHub Action's
    ``-d '{"limit": 100}'`` is honoured. (It was previously a query param, so the
    body was silently ignored and every run collected only the 25-job default —
    surplus due jobs aged out past tolerance and were lost as "missed".)
    """
    return await collect_due_outcomes(req.limit)


@router.get("/outcomes/status")
async def get_outcome_collection_status(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    return await collection_status(db)


@router.get("/outcomes/health")
async def get_outcome_collector_health(
    window_days: int = 7,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """Full collector health: per-provider fetch reliability, recent job outcomes,
    and the last run summary. Durable (derived from usage_events + jobs), so a
    silently-failing collector reports non-OK even across a process restart."""
    return await collector_health(db, window_days=max(1, min(window_days, 90)))


@router.get("/operations/report")
async def get_operations_report(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """Measured reliability/economics inputs with explicit missing-cost coverage."""
    return await build_operations_report(db)


@router.get("/costs/per-analysis")
async def get_per_analysis_cost(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """Real measured Gemini cost per completed analysis over a recent window.

    Sums the perception + reasoning cost per analysis_id (from token counts × list
    price), then reports the distribution so a $9.99 unlimited seat can be checked
    against actual spend. Only analyses with recorded token cost are included."""
    days = max(1, min(days, 365))
    since = utc_now_naive() - timedelta(days=days)
    per_analysis = (await db.execute(
        select(
            UsageEvent.analysis_id,
            func.sum(UsageEvent.estimated_cost_micros),
            func.sum(UsageEvent.input_tokens),
            func.sum(UsageEvent.output_tokens),
        )
        .where(
            UsageEvent.operation.in_(("video_craft_perception", "video_craft_reasoning")),
            UsageEvent.analysis_id.isnot(None),
            UsageEvent.estimated_cost_micros.isnot(None),
            UsageEvent.created_at >= since,
        )
        .group_by(UsageEvent.analysis_id)
    )).all()

    costs = sorted(int(row[1]) for row in per_analysis if row[1] is not None)
    n = len(costs)

    def _usd(micros: float) -> float:
        return round(micros / 1_000_000, 4)

    if n == 0:
        return {
            "window_days": days,
            "analyses_costed": 0,
            "note": "No analyses with recorded token cost yet in this window.",
            "price_source": gemini_price_source(),
        }

    total = sum(costs)
    avg = total / n
    median = costs[n // 2]
    p90 = costs[min(n - 1, int(round(0.9 * (n - 1))))]
    return {
        "window_days": days,
        "analyses_costed": n,
        "avg_cost_micros": round(avg),
        "avg_cost_usd": _usd(avg),
        "median_cost_usd": _usd(median),
        "p90_cost_usd": _usd(p90),
        "max_cost_usd": _usd(costs[-1]),
        "total_cost_usd": _usd(total),
        # Break-even check against the $9.99/mo Pro price at the observed average.
        "pro_breakeven_analyses_per_month": round(9_990_000 / avg, 1) if avg else None,
        "price_source": gemini_price_source(),
    }


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

    if not isinstance(result, dict) or "error" in result or "seed_quality" not in result:
        detail = result.get("error", "invalid response") if isinstance(result, dict) else "invalid response"
        raise HTTPException(
            status_code=502,
            detail=f"Seed analysis failed ({detail}). Seed was NOT saved — please try again.",
        )

    try:
        rating = max(0, min(10, int(round(float(result["seed_quality"])))))
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

# ---------------------------------------------------------------------------
# Door A: automated seed harvest
# ---------------------------------------------------------------------------

class HarvestRequest(BaseModel):
    niches: Optional[list[str]] = None       # None = all 50
    min_views: int = 500_000
    max_views: Optional[int] = None          # None = no cap (use for low-quality seed harvests)
    max_per_niche: int = 3
    platform: str = "tiktok"                 # "tiktok" | "instagram"
    min_likes: int = 1_000                   # Instagram only


@router.post("/harvest")
async def trigger_harvest(
    background_tasks: BackgroundTasks,
    req: HarvestRequest = HarvestRequest(),
    _: None = Depends(check_admin),
):
    platform = req.platform.lower() if req.platform.lower() in ("tiktok", "instagram") else "tiktok"
    if platform == "instagram" and not os.getenv("HIKERAPI_KEY"):
        raise HTTPException(
            status_code=400,
            detail=(
                "HIKERAPI_KEY is not set. Add it to your Railway environment variables "
                "to run Instagram harvest. TikTok harvest does not require this key."
            ),
        )
    target = req.niches or list(NICHE_KEYWORDS.keys())
    if platform == "instagram":
        background_tasks.add_task(harvest_instagram_all, target, req.min_likes, req.max_per_niche)
    else:
        background_tasks.add_task(harvest_all, target, req.min_views, req.max_per_niche, req.max_views)
    return {"status": "harvest started", "niches": len(target), "platform": platform}


@router.get("/harvest/status")
async def get_harvest_status(
    _: None = Depends(check_admin),
):
    tiktok = get_last_harvest() or {"status": "never_run"}
    instagram = get_last_instagram_harvest() or {"status": "never_run"}
    return {"tiktok": tiktok, "instagram": instagram}


@router.post("/insights/generate")
async def generate_insights(
    platform: str = Form("tiktok"),
    niche: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """Generate (or regenerate) niche intelligence summaries from the seed library.
    If niche is provided, regenerate only that niche. Otherwise regenerate all niches
    that have enough rated seeds (>= 3). Returns a summary of what was generated.

    Also loads safe user corrections (thinking/deep, ≤120d, un-nudged) per niche and
    passes them to the insight generator so the synthesis captures both seed patterns
    AND real-world calibration signal in one unified prompt.
    """
    from collections import defaultdict
    from datetime import timedelta

    seeds_result = await db.execute(
        select(SeedVideo).where(SeedVideo.platform == platform)
    )
    all_seeds = seeds_result.scalars().all()

    # Group seeds by niche, filter to only niches with rated seeds
    by_niche: dict[str, list] = defaultdict(list)
    for s in all_seeds:
        if s.rating is not None:
            by_niche[s.niche].append(s)

    # Load safe corrections for this platform (all niches at once, filter in Python).
    # Same filtering rules as calibration.py: safe, un-nudged, thinking/deep, ≤120d.
    corrections_cutoff = utc_now_naive() - timedelta(days=120)
    corr_rows = (await db.execute(
        select(UserAnalysis).where(
            UserAnalysis.platform == platform,
            UserAnalysis.correction_json.is_not(None),
            UserAnalysis.counts_fetched_at >= corrections_cutoff,
        )
    )).scalars().all()

    corrections_by_niche: dict[str, list] = defaultdict(list)
    for r in corr_rows:
        try:
            c = json.loads(r.correction_json)
        except (ValueError, TypeError):
            continue
        if not isinstance(c, dict):
            continue
        if c.get("safe_to_learn_from") is not True:
            continue
        if c.get("audited_calibration_version", 0) != 0:
            continue
        if c.get("mode") not in ("thinking", "deep_thinking"):
            continue
        cn = r.canonical_niche or ""
        if cn:
            corrections_by_niche[cn].append(c)

    target_niches = [niche] if niche else list(by_niche.keys())
    results = []

    for n in target_niches:
        seeds = by_niche.get(n, [])
        if len(seeds) < 3:
            results.append({"niche": n, "status": "skipped", "reason": f"only {len(seeds)} rated seeds"})
            continue
        niche_corrections = corrections_by_niche.get(n, [])
        try:
            insight_text = await generate_niche_insight(seeds, platform, n, corrections=niche_corrections)
        except Exception as e:
            results.append({"niche": n, "status": "error", "reason": str(e)})
            continue

        # Upsert — update if exists, insert if not
        existing_result = await db.execute(
            select(NicheInsight).where(
                NicheInsight.platform == platform,
                NicheInsight.niche == n,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            existing.insight = insight_text
            existing.seed_count = len(seeds)
            existing.generated_at = utc_now_naive()
        else:
            db.add(NicheInsight(
                platform=platform,
                niche=n,
                insight=insight_text,
                seed_count=len(seeds),
            ))
        await db.commit()
        results.append({
            "niche": n,
            "status": "generated",
            "seed_count": len(seeds),
            "correction_count": len(niche_corrections),
        })

    generated = sum(1 for r in results if r["status"] == "generated")
    return {"platform": platform, "generated": generated, "total": len(target_niches), "results": results}


@router.get("/insights")
async def get_insights(
    platform: str = "tiktok",
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """List all generated niche insights for a platform."""
    result = await db.execute(
        select(NicheInsight)
        .where(NicheInsight.platform == platform)
        .order_by(NicheInsight.niche)
    )
    rows = result.scalars().all()
    return [
        {
            "niche": r.niche,
            "seed_count": r.seed_count,
            "generated_at": r.generated_at,
            "insight_preview": r.insight[:200] + "..." if len(r.insight) > 200 else r.insight,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Calibration notes (Build #3) — mistake summarization from real corrections
# ---------------------------------------------------------------------------

@router.post("/calibration/generate")
async def generate_calibration(
    platform: str = Form("tiktok"),
    niche: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """Regenerate calibration notes FROM SCRATCH from the safe corrections in
    user_analyses. If `niche` is given, only that one (pass "GLOBAL" for the
    cross-niche note). Otherwise: every niche that has any correction, plus GLOBAL.
    Niches below the correction floor are skipped (no note written) — that is the
    safe default. Never stacks: each note is rebuilt from raw corrections + clamped."""
    if niche:
        target_niches = [niche]
    else:
        # Candidate niches = canonical labels with at least one stored correction for
        # this platform. Use canonical_niche (not raw) so notes key the same way
        # load_calibration_note() reads them at grading time.
        niche_rows = (await db.execute(
            select(UserAnalysis.canonical_niche)
            .where(
                UserAnalysis.platform == platform,
                UserAnalysis.correction_json.is_not(None),
            )
            .distinct()
        )).scalars().all()
        target_niches = sorted({n for n in niche_rows if n}) + [GLOBAL_NICHE]

    results = []
    for n in target_niches:
        try:
            note = await generate_calibration_note(platform, n)
        except ValueError as e:
            # Below floor — caller falls back to GLOBAL or skips. No note written.
            results.append({"niche": n, "status": "skipped", "reason": str(e)})
            continue
        except Exception as e:  # noqa: BLE001
            results.append({"niche": n, "status": "error", "reason": str(e)})
            continue

        existing = (await db.execute(
            select(CalibrationNote).where(
                CalibrationNote.platform == platform,
                CalibrationNote.niche == n,
            )
        )).scalar_one_or_none()
        if existing:
            existing.note_json = json.dumps(note)
            existing.sample_count = note["sample_count"]
            existing.generated_at = utc_now_naive()
        else:
            db.add(CalibrationNote(
                platform=platform,
                niche=n,
                note_json=json.dumps(note),
                sample_count=note["sample_count"],
            ))
        await db.commit()
        results.append({
            "niche": n,
            "status": "generated",
            "sample_count": note["sample_count"],
            "confidence": note.get("confidence"),
            "overall_tendency": note.get("overall_tendency"),
        })

    generated = sum(1 for r in results if r["status"] == "generated")
    return {"platform": platform, "generated": generated, "total": len(target_niches), "results": results}


@router.get("/calibration")
async def get_calibration(
    platform: str = "tiktok",
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """List all stored calibration notes for a platform."""
    rows = (await db.execute(
        select(CalibrationNote)
        .where(CalibrationNote.platform == platform)
        .order_by(CalibrationNote.niche)
    )).scalars().all()
    out = []
    for r in rows:
        try:
            note = json.loads(r.note_json)
        except (ValueError, TypeError):
            note = {}
        out.append({
            "niche": r.niche,
            "sample_count": r.sample_count,
            "generated_at": r.generated_at,
            "confidence": note.get("confidence"),
            "overall_tendency": note.get("overall_tendency"),
            "directive": note.get("directive"),
            "dimension_adjustments": note.get("dimension_adjustments"),
            "caveats": note.get("caveats"),
        })
    return out


# ---------------------------------------------------------------------------
# Trend Feed harvest (recently high-performing videos — velocity-filtered)
# ---------------------------------------------------------------------------

class TrendHarvestRequest(BaseModel):
    niches: Optional[list[str]] = None
    max_age_days: int = 30
    min_velocity: float = 20_000   # views/day
    max_per_niche: int = 2


@router.post("/trends/harvest")
async def trigger_trend_harvest(
    background_tasks: BackgroundTasks,
    req: TrendHarvestRequest = TrendHarvestRequest(),
    _: None = Depends(check_admin),
):
    """Trigger a trending video harvest. Pulls recent high-performing TikTok videos
    (published in last max_age_days) filtered by view velocity (views/day).
    Run after regular harvest to populate the trend signal layer."""
    target = req.niches or list(NICHE_KEYWORDS.keys())
    background_tasks.add_task(
        harvest_trending, target, req.max_age_days, req.min_velocity, req.max_per_niche
    )
    return {
        "status": "trend harvest started",
        "niches": len(target),
        "max_age_days": req.max_age_days,
        "min_velocity": req.min_velocity,
    }


@router.get("/trends/harvest/status")
async def get_trend_harvest_status(_: None = Depends(check_admin)):
    return get_last_trend_harvest() or {"status": "never_run"}


# ---------------------------------------------------------------------------
# Trend Intelligence — delta synthesis from recent vs established seeds
# ---------------------------------------------------------------------------

@router.post("/trends/generate")
async def generate_trends(
    platform: str = Form("tiktok"),
    niche: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """Generate (or regenerate) trend delta summaries for niches that have
    enough recent seeds (< 30 days old). If niche is provided, only that niche.
    """
    seeds_result = await db.execute(
        select(SeedVideo).where(SeedVideo.platform == platform)
    )
    all_seeds = seeds_result.scalars().all()

    from collections import defaultdict
    by_niche: dict[str, list] = defaultdict(list)
    for s in all_seeds:
        if s.rating is not None:
            by_niche[s.niche].append(s)

    target_niches = [niche] if niche else list(by_niche.keys())
    results = []

    for n in target_niches:
        seeds = by_niche.get(n, [])
        try:
            trend_text = await generate_trend_insight(seeds, platform, n)
        except ValueError as e:
            results.append({"niche": n, "status": "skipped", "reason": str(e)})
            continue
        except Exception as e:
            results.append({"niche": n, "status": "error", "reason": str(e)})
            continue

        from datetime import timezone, timedelta
        from services.trend_insights import RECENT_WINDOW_DAYS, ESTABLISHED_MIN_DAYS, _ref_date
        now_utc = datetime.now(timezone.utc)
        recent_cutoff = now_utc - timedelta(days=RECENT_WINDOW_DAYS)
        established_cutoff = now_utc - timedelta(days=ESTABLISHED_MIN_DAYS)
        recent_count = sum(1 for s in seeds if _ref_date(s) and _ref_date(s) >= recent_cutoff)
        established_count = sum(1 for s in seeds if _ref_date(s) and _ref_date(s) < established_cutoff)

        existing_result = await db.execute(
            select(TrendSummary).where(
                TrendSummary.platform == platform,
                TrendSummary.niche == n,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            existing.trend_text = trend_text
            existing.recent_seed_count = recent_count
            existing.established_seed_count = established_count
            existing.generated_at = utc_now_naive()
        else:
            db.add(TrendSummary(
                platform=platform,
                niche=n,
                trend_text=trend_text,
                recent_seed_count=recent_count,
                established_seed_count=established_count,
            ))
        await db.commit()
        results.append({"niche": n, "status": "generated", "recent_count": recent_count})

    generated = sum(1 for r in results if r["status"] == "generated")
    return {"platform": platform, "generated": generated, "total": len(target_niches), "results": results}


@router.get("/trends")
async def get_trends(
    platform: str = "tiktok",
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """List all generated trend summaries for a platform."""
    result = await db.execute(
        select(TrendSummary)
        .where(TrendSummary.platform == platform)
        .order_by(TrendSummary.niche)
    )
    rows = result.scalars().all()
    return [
        {
            "niche": r.niche,
            "recent_seed_count": r.recent_seed_count,
            "established_seed_count": r.established_seed_count,
            "generated_at": r.generated_at,
            "trend_preview": r.trend_text[:200] + "..." if len(r.trend_text) > 200 else r.trend_text,
        }
        for r in rows
    ]


@router.get("/api-usage")
async def get_api_usage(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_admin),
):
    """Successful Instagram URL fetches this calendar month vs the 20/month free limit."""
    now = utc_now_naive()
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

    usage_rows = (await db.execute(
        select(
            UsageEvent.provider,
            UsageEvent.operation,
            func.count(UsageEvent.id),
            func.sum(case((UsageEvent.success.is_(True), 1), else_=0)),
            func.avg(UsageEvent.latency_ms),
            func.sum(UsageEvent.input_tokens),
            func.sum(UsageEvent.output_tokens),
            func.sum(UsageEvent.estimated_cost_micros),
        )
        .where(UsageEvent.created_at >= now - timedelta(days=30))
        .group_by(UsageEvent.provider, UsageEvent.operation)
        .order_by(UsageEvent.provider, UsageEvent.operation)
    )).all()

    return {
        "instagram": {
            "used": used,
            "limit": 20,
            "resets_at": resets_at.strftime("%Y-%m-%d"),
        },
        "metered_operations_30d": [
            {
                "provider": provider,
                "operation": operation,
                "calls": calls,
                "successful_calls": successes or 0,
                "average_latency_ms": round(avg_latency or 0),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "verified_cost_micros": verified_cost,
            }
            for provider, operation, calls, successes, avg_latency,
            input_tokens, output_tokens, verified_cost in usage_rows
        ],
        "cost_status": "estimated_from_token_counts_and_list_price",
        "price_source": gemini_price_source(),
    }
