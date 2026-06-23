"""Durable collection of fixed-maturity public outcome snapshots.

An external scheduler may call the protected admin endpoint periodically. Jobs
outside their tolerance window are marked missed instead of silently labeling a
late observation as 24h/7d/30d data.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from database import AsyncSessionLocal
from models import OutcomeCollectionJob, UserAnalysis
from services.instagram_fetch import fetch_instagram_likes
from services.outcomes import add_outcome_snapshot, post_id_from_url, upsert_artifact, utc_now_naive
from services.tiktok_fetch import fetch_tiktok

MAX_ATTEMPTS = 3
_TARGET_HOURS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}


async def collection_status(db) -> dict:
    rows = (await db.execute(
        select(OutcomeCollectionJob.status, func.count())
        .group_by(OutcomeCollectionJob.status)
    )).all()
    counts = {status: count for status, count in rows}
    next_due = (await db.execute(
        select(OutcomeCollectionJob.due_at)
        .where(OutcomeCollectionJob.status == "pending")
        .order_by(OutcomeCollectionJob.due_at.asc())
        .limit(1)
    )).scalar_one_or_none()
    return {"counts": counts, "next_due_at": next_due}


async def _collect_job(job_id: int) -> str:
    now = utc_now_naive()
    async with AsyncSessionLocal() as db:
        job = (await db.execute(
            select(OutcomeCollectionJob).where(OutcomeCollectionJob.id == job_id)
        )).scalar_one_or_none()
        if job is None or job.status != "pending":
            return "skipped"
        if now > job.due_at + timedelta(hours=job.tolerance_hours):
            job.status = "missed"
            job.last_error = "Collector ran after the maturity tolerance window."
            job.completed_at = now
            await db.commit()
            return "missed"
        analysis = (await db.execute(
            select(UserAnalysis).where(UserAnalysis.id == job.analysis_id)
        )).scalar_one_or_none()
        if analysis is None or not analysis.video_url:
            job.status = "failed"
            job.last_error = "Analysis or linked post URL is unavailable."
            job.completed_at = now
            await db.commit()
            return "failed"
        platform = analysis.platform or "tiktok"
        url = analysis.video_url
        analysis_id = analysis.id
        posted_at = job.due_at - timedelta(hours=_TARGET_HOURS[job.horizon])

    try:
        if platform == "instagram":
            likes = await fetch_instagram_likes(url)
            metrics = {"views": None, "likes": likes, "comments": None, "shares": None,
                       "saves": None, "creator_followers": None, "provider_payload_hash": None}
            source = "rapidapi"
            meta = None
        else:
            meta = await fetch_tiktok(url)
            provider_posted_at = meta.get("posted_at")
            if provider_posted_at is not None:
                posted_at = provider_posted_at
            metrics = {
                "views": meta["view_count"], "likes": meta["like_count"],
                "comments": meta.get("comment_count"), "shares": meta.get("share_count"),
                "saves": meta.get("save_count"), "creator_followers": meta.get("creator_followers"),
                "provider_payload_hash": meta.get("provider_payload_hash"),
            }
            source = "tikwm"

        async with AsyncSessionLocal() as db:
            job = (await db.execute(
                select(OutcomeCollectionJob).where(OutcomeCollectionJob.id == job_id).with_for_update()
            )).scalar_one_or_none()
            analysis = (await db.execute(
                select(UserAnalysis).where(UserAnalysis.id == analysis_id)
            )).scalar_one_or_none()
            if job is None or job.status != "pending" or analysis is None:
                return "skipped"
            snapshot = add_outcome_snapshot(
                db, analysis_id=analysis_id, platform=platform, source=source,
                posted_at=posted_at, **metrics,
            )
            analysis.actual_views = metrics["views"] if metrics["views"] is not None else analysis.actual_views
            analysis.actual_likes = metrics["likes"]
            analysis.counts_fetched_at = utc_now_naive()
            if meta:
                await upsert_artifact(
                    db, analysis_id,
                    platform_post_id=meta.get("video_id") or post_id_from_url(url, "tiktok"),
                    creator_key=meta.get("author_handle"),
                )
            if snapshot.horizon != job.horizon:
                job.status = "missed"
                job.last_error = f"Observed at {snapshot.post_age_hours}h, outside {job.horizon} classification."
            else:
                job.status = "complete"
                job.last_error = None
            job.attempts += 1
            job.completed_at = utc_now_naive()
            await db.commit()
            return job.status
    except Exception as exc:
        async with AsyncSessionLocal() as db:
            job = (await db.execute(
                select(OutcomeCollectionJob).where(OutcomeCollectionJob.id == job_id).with_for_update()
            )).scalar_one_or_none()
            if job is None:
                return "skipped"
            # A concurrent run may have already finalized this job; never overwrite a
            # terminal state or miscount its outcome as a failure of this attempt.
            if job.status != "pending":
                return job.status
            job.attempts += 1
            job.last_error = f"{type(exc).__name__}: {exc}"[:500]
            if job.attempts >= MAX_ATTEMPTS or utc_now_naive() > job.due_at + timedelta(hours=job.tolerance_hours):
                job.status = "failed"
                job.completed_at = utc_now_naive()
            await db.commit()
            return job.status


async def collect_due_outcomes(limit: int = 25) -> dict:
    limit = max(1, min(limit, 100))
    async with AsyncSessionLocal() as db:
        job_ids = (await db.execute(
            select(OutcomeCollectionJob.id)
            .where(
                OutcomeCollectionJob.status == "pending",
                OutcomeCollectionJob.due_at <= utc_now_naive(),
            )
            .order_by(OutcomeCollectionJob.due_at.asc())
            .limit(limit)
        )).scalars().all()
    results = {"complete": 0, "missed": 0, "failed": 0, "pending": 0, "skipped": 0}
    for job_id in job_ids:
        status = await _collect_job(job_id)
        results[status] = results.get(status, 0) + 1
    return {"processed": len(job_ids), "results": results}
