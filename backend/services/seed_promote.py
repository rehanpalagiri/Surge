"""Door B (v1.20): auto-promote a user's verified, posted video into the seed library.

When a user links their posted TikTok (`analyze.link_video`), the view/like counts
are pulled live from tikwm — real, un-fakeable evidence, strictly better than a
hand-picked admin seed. We run that video through the SAME seed-analysis pipeline the
admin uses (the rating is anchored to the real counts, so a verified flop lands in the
LOW bucket and a verified hit in HIGH, automatically). The result is persisted as a
SeedVideo with ``source="user"``.

Runs as a FastAPI BackgroundTask so the user's stat-sync stays instant — seed analysis
uploads the video to Gemini and can take 30–120s. Every failure path is swallowed and
logged: promotion is a best-effort nicety, never part of the user's request guarantee.
"""

import os
import json
import uuid
import logging

import httpx
from sqlalchemy import select

from datetime import datetime

from auth import is_minor
from database import AsyncSessionLocal
from models import SeedVideo, UserAnalysis, User
from services.seed_analysis import analyze_seed_video
from services.niche_classifier import classify_niche
from services.tiktok_fetch import fetch_tiktok

logger = logging.getLogger("seed_promote")


async def _download(video_url: str, path: str) -> None:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
        async with c.stream("GET", video_url) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=65536):
                    f.write(chunk)


async def promote_analysis_to_seed(
    analysis_id: int, meta: dict | None = None, consent_override: bool = False
) -> None:
    """Background task. Idempotent and self-contained (opens its own DB session,
    since the request's session is already closed by the time this runs). Any
    failure is logged and swallowed — it must never surface to the user.

    ``meta``: the tikwm payload link_video just fetched. Passing it through avoids
    a second tikwm call <1s after the first — the free tier is rate-limited to
    ~1 req/sec, so the back-to-back re-fetch would risk a 429 on every promotion.
    Falls back to fetching when not supplied.

    ``consent_override``: True only from the explicit consent endpoint — the user
    just clicked "Yes" on the banner, so the "ask" gate is satisfied. Minors and
    "no" are still hard blocks even with the override.
    """
    file_path = None
    try:
        # --- Read phase: snapshot what we need, then release the session before
        #     the long Gemini round-trip (don't hold a txn open for minutes). ---
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(UserAnalysis).where(UserAnalysis.id == analysis_id)
            )
            a = res.scalar_one_or_none()
            if a is None or a.promoted_seed_id is not None:
                return  # gone or already promoted
            if (a.platform or "tiktok") != "tiktok" or not a.video_url:
                return  # only verified TikTok links are promotable

            # --- Consent gate (v1.24) ---
            consent = "ask"
            if a.user_id is not None:
                ures = await db.execute(select(User).where(User.id == a.user_id))
                owner = ures.scalar_one_or_none()
                if owner is None:
                    return
                if is_minor(owner):
                    return  # minors are excluded unconditionally
                consent = owner.seed_consent or "ask"
            if consent == "no":
                return
            if consent == "ask" and not consent_override:
                # Park it — the results page shows the consent banner and the
                # explicit decision endpoint re-runs us with the override.
                a.pending_seed_consent = True
                await db.commit()
                return

            page_url = a.video_url
            raw_niche = a.niche

        # --- Heavy phase (no open session): classify the niche and (if not handed
        #     to us) fetch metadata for the downloadable play URL + counts. ---
        canonical = await classify_niche(raw_niche or "")
        if meta is None:
            meta = await fetch_tiktok(page_url)
        view_count = meta["view_count"]
        like_count = meta["like_count"]

        uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, f"seed_{uuid.uuid4()}.mp4")
        await _download(meta["video_url"], file_path)

        result = await analyze_seed_video(
            file_path, "tiktok", canonical, view_count, like_count
        )
        if not isinstance(result, dict) or "virality_rating" not in result:
            logger.warning(
                "promote %s: seed analysis failed: %s",
                analysis_id,
                result.get("error") if isinstance(result, dict) else result,
            )
            return
        try:
            rating = max(0, min(10, int(round(float(result["virality_rating"])))))
        except (ValueError, TypeError):
            logger.warning("promote %s: non-numeric rating, skipping", analysis_id)
            return

        # --- Write phase: re-check idempotency inside the write txn (guards against
        #     two refreshes racing), persist the seed, stamp the analysis.
        #     with_for_update locks the row so a second concurrent promote blocks
        #     here until the first commits, then sees promoted_seed_id set and bails
        #     (no-op on SQLite, which uses db-level locking). ---
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(UserAnalysis).where(UserAnalysis.id == analysis_id).with_for_update()
            )
            a = res.scalar_one_or_none()
            if a is None or a.promoted_seed_id is not None:
                return
            seed = SeedVideo(
                filename=f"user-{analysis_id}-{uuid.uuid4().hex[:8]}",
                platform="tiktok",
                niche=canonical,
                view_count=view_count,
                like_count=like_count,
                rating=rating,
                gemini_analysis=json.dumps(result),
                notes="Auto-promoted from a verified user-posted video.",
                source="user",
            )
            db.add(seed)
            await db.flush()  # populate seed.id
            a.promoted_seed_id = seed.id
            a.pending_seed_consent = False
            await db.commit()
            logger.info(
                "promote %s -> seed %s (rating %s, niche %s, %s views)",
                analysis_id, seed.id, rating, canonical, view_count,
            )
    except Exception as e:  # noqa: BLE001 — promotion must never crash the request
        logger.warning("promote %s: failed: %s", analysis_id, e)
    finally:
        if file_path:
            try:
                os.remove(file_path)
            except OSError:
                pass
