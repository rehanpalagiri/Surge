"""Outcome snapshots and dataset identity helpers.

All writes are additive. Outcome rows are never updated, so 24h/7d/30d
observations remain distinguishable instead of being overwritten by a refresh.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from models import AnalysisArtifact, OutcomeCollectionJob, OutcomeSnapshot


_HORIZONS = (
    ("24h", 24, 6),
    ("7d", 24 * 7, 24),
    ("30d", 24 * 30, 72),
)


def utc_now_naive() -> datetime:
    """Return UTC without tzinfo, matching the existing DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def integrity_flags(
    *,
    source: str,
    views: int | None,
    likes: int | None,
    comments: int | None = None,
    shares: int | None = None,
) -> list[str]:
    """Flag known limitations without pretending to detect bots or paid traffic."""
    flags = []
    if source in ("tikwm", "rapidapi", "hikerapi"):
        flags.extend(("third_party_metrics", "paid_status_unknown", "automated_activity_unknown"))
    values = {"views": views, "likes": likes, "comments": comments, "shares": shares}
    if any(v is not None and v < 0 for v in values.values()):
        flags.append("negative_metric")
    if views is not None and likes is not None and likes > views:
        flags.append("likes_exceed_views")
    if views == 0 and any((v or 0) > 0 for v in (likes, comments, shares)):
        flags.append("engagement_without_views")
    return flags


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def post_id_from_url(url: str, platform: str) -> str | None:
    pattern = r"/video/(\d+)" if platform == "tiktok" else r"/(?:reel|reels)/([^/?#]+)"
    match = re.search(pattern, url or "", re.IGNORECASE)
    return match.group(1) if match else None


def maturity_window(posted_at: datetime | None, observed_at: datetime) -> tuple[int | None, str | None]:
    if posted_at is None:
        return None, None
    if posted_at.tzinfo is not None:
        posted_at = posted_at.replace(tzinfo=None)
    if observed_at.tzinfo is not None:
        observed_at = observed_at.replace(tzinfo=None)
    age_hours = max(0, round((observed_at - posted_at).total_seconds() / 3600))
    matches = [
        (abs(age_hours - target), label)
        for label, target, tolerance in _HORIZONS
        if abs(age_hours - target) <= tolerance
    ]
    return age_hours, min(matches)[1] if matches else None


async def upsert_artifact(
    db,
    analysis_id: int,
    *,
    content_sha256: str | None = None,
    platform_post_id: str | None = None,
    creator_key: str | None = None,
) -> None:
    row = (await db.execute(
        select(AnalysisArtifact).where(AnalysisArtifact.analysis_id == analysis_id)
    )).scalar_one_or_none()
    if row is None:
        row = AnalysisArtifact(analysis_id=analysis_id)
        db.add(row)
    if content_sha256:
        row.content_sha256 = content_sha256
    if platform_post_id:
        row.platform_post_id = platform_post_id
    if creator_key:
        row.creator_key = creator_key.strip().lstrip("@").lower()
    row.updated_at = utc_now_naive()


def add_outcome_snapshot(
    db,
    *,
    analysis_id: int,
    platform: str,
    source: str,
    views: int | None,
    likes: int | None,
    posted_at: datetime | None = None,
    comments: int | None = None,
    shares: int | None = None,
    saves: int | None = None,
    creator_followers: int | None = None,
    provider_payload_hash: str | None = None,
    integrity_flags_json: str | None = None,
) -> OutcomeSnapshot:
    observed_at = utc_now_naive()
    age_hours, horizon = maturity_window(posted_at, observed_at)
    base_flags = integrity_flags(
        source=source, views=views, likes=likes, comments=comments, shares=shares
    )
    supplied_flags = []
    if integrity_flags_json:
        try:
            parsed = json.loads(integrity_flags_json)
            if isinstance(parsed, list):
                supplied_flags = [str(v) for v in parsed]
        except (TypeError, ValueError):
            supplied_flags = ["invalid_integrity_metadata"]
    integrity_flags_json = json.dumps(list(dict.fromkeys(base_flags + supplied_flags)))
    row = OutcomeSnapshot(
        analysis_id=analysis_id,
        platform=platform,
        source=source,
        observed_at=observed_at,
        posted_at=posted_at,
        post_age_hours=age_hours,
        horizon=horizon,
        views=views,
        likes=likes,
        comments=comments,
        shares=shares,
        saves=saves,
        creator_followers=creator_followers,
        metric_version="observed_response_v1",
        provider_payload_hash=provider_payload_hash,
        integrity_flags_json=integrity_flags_json,
    )
    db.add(row)
    return row


async def schedule_outcome_jobs(
    db,
    *,
    analysis_id: int,
    posted_at: datetime | None,
    captured_horizon: str | None = None,
) -> int:
    """Create one durable job per future maturity window; never backfill a missed age."""
    if posted_at is None:
        return 0
    if posted_at.tzinfo is not None:
        posted_at = posted_at.replace(tzinfo=None)
    now = utc_now_naive()
    created = 0
    for label, target_hours, tolerance_hours in _HORIZONS:
        exists = (await db.execute(
            select(OutcomeCollectionJob.id).where(
                OutcomeCollectionJob.analysis_id == analysis_id,
                OutcomeCollectionJob.horizon == label,
            )
        )).scalar_one_or_none()
        if exists is not None:
            continue
        due_at = posted_at + timedelta(hours=target_hours)
        if captured_horizon == label:
            status, completed_at, last_error = "complete", now, None
        elif now > due_at + timedelta(hours=tolerance_hours):
            status, completed_at, last_error = "missed", now, "Maturity window passed before scheduling."
        else:
            status, completed_at, last_error = "pending", None, None
        db.add(OutcomeCollectionJob(
            analysis_id=analysis_id,
            horizon=label,
            due_at=due_at,
            tolerance_hours=tolerance_hours,
            status=status,
            completed_at=completed_at,
            last_error=last_error,
        ))
        created += 1
    return created
