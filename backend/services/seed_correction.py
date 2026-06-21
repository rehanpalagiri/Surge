import json
import logging

from sqlalchemy import select
from google.genai import types

from database import AsyncSessionLocal
from models import UserAnalysis
from services.gemini import client

log = logging.getLogger("seed_correction")


def _build_correction_prompt(prediction: dict, actual_views, actual_likes, niche: str) -> str:
    if actual_views and actual_views > 0:
        like_rate = actual_likes / actual_views
        outcome_line = (
            f"Views: {actual_views:,} | Likes: {actual_likes:,} | Like-rate: {like_rate*100:.2f}%"
        )
        rate_note = (
            "Like-rate is your truth signal for CONTENT quality (reach-normalized). "
            ">10% strong, 5-10% good, 2-5% average, <2% weak."
        )
    else:
        outcome_line = f"Likes: {actual_likes:,} (views hidden — like-rate uncomputable)"
        rate_note = "No like-rate available → you cannot reliably audit content; set gap_explained_by='unclear'."

    return f"""ROLE: You are auditing ONE past Surge prediction against the real outcome to find where our scoring was miscalibrated. The reader is another AI. Be conservative and honest.

NICHE: {niche}

OUR ORIGINAL PREDICTION (made BEFORE the user posted):
- overall_score: {prediction.get('overall_score')}
- hook_velocity: {prediction.get('hook_velocity')}
- cut_frequency: {prediction.get('cut_frequency')}
- text_scannability: {prediction.get('text_scannability')}
- curiosity_gap: {prediction.get('curiosity_gap')}
- audio_visual_sync: {prediction.get('audio_visual_sync')}
- loop_seamlessness: {prediction.get('loop_seamlessness')}
- verdict: {prediction.get('verdict')}

REAL OUTCOME (measured after posting):
{outcome_line}
{rate_note}

THE RULE THAT PREVENTS POISONING (apply strictly):
Before blaming our CONTENT scores, rule out DISTRIBUTION.
- Weak outcome + low like-rate can mean the video flopped on REACH (small account, no push),
  NOT on content. In that case our scores may have been FINE → gap_explained_by='distribution',
  safe_to_learn_from=false.
- Only flag a scoring error when the like-rate DIRECTLY contradicts a dimension score —
  e.g. we scored hook_velocity 8 but a 0.4% like-rate means almost no one engaged.

You have NO watch-time data. You can ONLY audit at the WHOLE-VIDEO level, not per-second.
When unsure, prefer safe_to_learn_from=false. A wrong correction is worse than no correction.

Return ONLY valid JSON:
{{
  "gap": "we predicted <verdict / overall_score>, reality was <one-line outcome>",
  "gap_explained_by": "content" | "distribution" | "unclear",
  "safe_to_learn_from": true | false,
  "likely_miscalibrated_dimension": "<one of the 6 dimension names, or null>",
  "direction": "we_over_rated" | "we_under_rated" | null,
  "confidence": "low" | "medium" | "high",
  "note": "<one sentence, plain, what calibration lesson this single case suggests — or 'none'>"
}}"""


# Below this view count the outcome is immature/noise — a correction computed on a
# just-posted video would record a wrong "flop". We skip without writing; a later
# refresh re-runs once the late-bloomer has real signal. (Hole A + B.)
MIN_VIEWS_FOR_CORRECTION = 5_000


async def audit_prediction(analysis_id: int) -> None:
    """Background task. Opens its own session. Best-effort: every failure swallowed.
    Reads the analysis's prediction + real counts, runs a text-only correction pass,
    stores the result in UserAnalysis.correction_json.

    Re-runs on every link/refresh and OVERWRITES — like-rate isn't stable at the maturity
    floor (early viewers skew toward followers), so the correction tracks the latest data
    rather than freezing on the first reading. Flip to write-once by re-adding
    `or a.correction_json is not None` to the first guard."""
    from auth import is_minor
    from models import User
    try:
        async with AsyncSessionLocal() as db:
            a = (await db.execute(
                select(UserAnalysis).where(UserAnalysis.id == analysis_id)
            )).scalar_one_or_none()
            if a is None or a.actual_likes is None:
                return
            # Hole A + B: only audit a MATURE outcome. Below the floor, return WITHOUT
            # writing so a later refresh re-runs once the video has real signal.
            if (a.actual_views or 0) < MIN_VIEWS_FOR_CORRECTION:
                return
            # Hole C: respect consent — skip minors and users who opted out of data use.
            # (link_video requires auth, so user_id is always set here, but guard anyway.)
            if a.user_id is not None:
                owner = (await db.execute(
                    select(User).where(User.id == a.user_id)
                )).scalar_one_or_none()
                if owner is not None and (is_minor(owner) or (owner.seed_consent or "ask") == "no"):
                    return
            try:
                pred = json.loads(a.scores_json)
            except (ValueError, TypeError):
                return
            if not isinstance(pred, dict) or "error" in pred or not pred.get("overall_score"):
                return
            niche, views, likes, mode = a.niche, a.actual_views, a.actual_likes, (a.mode or "quick")
            # Build #3 (hole #2): which calibration version nudged the audited prediction.
            # Non-zero means the prediction was already calibration-adjusted, so the next
            # calibration generation must EXCLUDE this correction (never correct a correction).
            cal_version = a.calibration_version or 0

        prompt = _build_correction_prompt(pred, views, likes, niche)
        resp = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        # Only persist a well-formed correction — never store junk for the summarizer.
        try:
            correction = json.loads(resp.text)
        except (ValueError, TypeError):
            return
        if not isinstance(correction, dict) or "gap_explained_by" not in correction:
            return
        # Hole D: tag provenance so the future mistake-summary can separate weak "quick"
        # predictions from strong "deep" ones, and know which maturity it audited at.
        correction["mode"] = mode
        correction["audited_at_views"] = views
        correction["audited_calibration_version"] = cal_version

        # Overwrite (recompute-on-refresh); row-lock to serialize concurrent link/refresh
        # tasks so two can't double-write (no-op on SQLite, real lock on Postgres).
        async with AsyncSessionLocal() as db:
            a = (await db.execute(
                select(UserAnalysis)
                .where(UserAnalysis.id == analysis_id)
                .with_for_update()
            )).scalar_one_or_none()
            if a is None:
                return
            a.correction_json = json.dumps(correction)
            await db.commit()
            log.info("corrected analysis %s @%s views (%s): %s",
                     analysis_id, views, mode, correction.get("gap_explained_by"))

    except Exception as e:  # noqa: BLE001 — never crash the request
        log.warning("audit_prediction %s failed: %s", analysis_id, e)
