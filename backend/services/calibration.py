"""Mistake Summarization / Calibration (Build #3).

Aggregates the `safe_to_learn_from=true` corrections written by `audit_prediction`
(Build #5) into a single bounded calibration note per (platform, niche), or the
literal "GLOBAL" pseudo-niche. The note tells the grader where CraftLint systematically
over- or under-rates, as soft guidance — NOT hard math.

The real danger here was never accuracy — it was runaway self-reinforcement and
selection-bias inflation. The guards that matter:
  - ONLY consume corrections flagged safe_to_learn_from (hole #1).
  - Regenerate FROM SCRATCH every run — never stack on a prior note (hole #2).
  - Exclude predictions that already carried a calibration nudge, so we never
    "correct a correction" into drift (hole #2).
  - Keep only thinking/deep predictions — quick ones are structurally weak (hole #4).
  - Cap every adjustment server-side after the model returns; upward nudges are
    capped TIGHTER than downward because users link successes more than failures,
    so an under-rate signal is partly an artifact (hole #3).
  - Below a per-niche floor, refuse to generate — caller falls back to GLOBAL or
    skips (hole #5). A wrong correction is worse than no correction.

Inert until corrections accumulate past MIN_CORRECTIONS, the note is generated
(admin trigger), and grading injection is wired (gemini._build_system_prompt).
"""

import json
import logging
import os
from datetime import datetime, timedelta
from services.clock import utc_now_naive

from sqlalchemy import select
from google.genai import types

from database import AsyncSessionLocal
from models import UserAnalysis, CalibrationNote
from services.gemini import client, _GRADING_SYSTEM_INSTRUCTION
from services.telemetry import tracked_generate_content

log = logging.getLogger("calibration")

# Sentinel niche for the cross-niche fallback note.
GLOBAL_NICHE = "GLOBAL"


def calibration_enabled() -> bool:
    """Master kill-switch for the AI-audits-AI calibration path
    (correction audit → calibration note → grading nudge).

    Defaults OFF and is read at call time (not import) so nothing in this dormant
    path can influence a live craft score unless an operator EXPLICITLY enables it.
    Before it is ever turned on, a drift metric must be in place (see
    backend/tools/craft_correlation.py) to catch the runaway self-reinforcement /
    selection-bias inflation this path risks. Every entry point — note generation,
    the correction audit, and the grade-time note read — checks this first."""
    return os.getenv("SURGE_CALIBRATION_ENABLED", "").strip().lower() in (
        "1", "true", "yes", "on",
    )

MIN_CORRECTIONS = 12        # FIX hole #5: below this per niche, do not generate a niche note
MIN_PER_DIMENSION = 5       # FIX hole #4: a dimension nudge needs this many corrections naming it
RECENCY_WINDOW_DAYS = 120   # FIX hole #5: ignore corrections older than this
MAX_DOWN = 1.0              # FIX hole #2/#3: cap a downward nudge
MAX_UP = 0.5               # FIX hole #3: upward nudge capped TIGHTER (selection bias)

_DIMENSIONS = (
    "hook_velocity",
    "cut_frequency",
    "text_scannability",
    "curiosity_gap",
    "audio_visual_sync",
    "loop_seamlessness",
)


def note_version(generated_at: datetime) -> int:
    """Stable non-zero integer identifying a stored note, derived from its
    generation time. Stamped onto predictions nudged by this note so the next
    generation can exclude them (hole #2). Any non-zero value works; the epoch
    second is monotonic across regenerations of the same (platform, niche)."""
    return int(generated_at.timestamp())


async def load_calibration_note(db, platform: str, niche: str) -> dict | None:
    """Load the calibration note to apply when grading a (platform, niche) video.
    Prefers the niche-specific note; falls back to the platform's GLOBAL note when
    the niche has none (acceptance #6). Returns the parsed note dict with a non-zero
    `version` stamped in, or None when no note exists. Never raises — calibration is
    optional enrichment, so any failure means "grade un-nudged".

    NOTE: returns the note regardless of confidence/sample_count — the gemini grader
    decides whether to actually apply it (see _calibration_applies). This keeps the
    application gate in one place."""
    # Grade-time injection fence: with the calibration path disabled (default),
    # never hand a note to the grader, even if one exists in the table. This is the
    # single point any future grading wire-up must pass through, so the flag alone
    # keeps grading un-nudged.
    if not calibration_enabled():
        return None
    try:
        row = (await db.execute(
            select(CalibrationNote).where(
                CalibrationNote.platform == platform,
                CalibrationNote.niche == niche,
            )
        )).scalar_one_or_none()
        if row is None and niche != GLOBAL_NICHE:
            row = (await db.execute(
                select(CalibrationNote).where(
                    CalibrationNote.platform == platform,
                    CalibrationNote.niche == GLOBAL_NICHE,
                )
            )).scalar_one_or_none()
        if row is None:
            return None
        note = json.loads(row.note_json)
        if not isinstance(note, dict):
            return None
        note["version"] = note_version(row.generated_at)
        return note
    except Exception as e:  # noqa: BLE001 — calibration is best-effort
        log.warning("load_calibration_note %s/%s failed: %s", platform, niche, e)
        return None


def _build_calibration_prompt(
    niche: str, corrections: list, min_per_dim: int, max_down: float, max_up: float
) -> str:
    # Trim each correction to the fields the auditor needs — never feed raw rows.
    slim = [
        {
            "gap": c.get("gap"),
            "direction": c.get("direction"),
            "likely_miscalibrated_dimension": c.get("likely_miscalibrated_dimension"),
            "confidence": c.get("confidence"),
            "audited_at_views": c.get("audited_at_views"),
        }
        for c in corrections
    ]
    corrections_json = json.dumps(slim, indent=2)
    return f"""ROLE: You are a calibration auditor for the CraftLint video scoring AI. You are given a batch of
post-hoc corrections — each one compares a past CraftLint prediction to the REAL outcome. Find ONLY
systematic, consistent miscalibrations. The reader is another AI.

NICHE: {niche}

CORRECTIONS (already filtered to safe-to-learn-from, thinking/deep mode, recent):
{corrections_json}
(each: gap, direction, likely_miscalibrated_dimension, confidence, audited_at_views)

RULES (apply strictly):
1. A miscalibration counts ONLY if it is CONSISTENT across many corrections in the SAME direction.
   A signal from 2-3 corrections is noise — ignore it.
2. A per-dimension adjustment requires at least {min_per_dim} corrections naming THAT dimension.
   You have NO watch-time data, so per-dimension blame is uncertain — prefer the WHOLE-VIDEO
   over/under-rating signal and keep per-dimension nudges small.
3. SELECTION BIAS WARNING: users link their successes more than their failures, so "we under-rated"
   is partly an artifact. Treat an under-rate signal with extra skepticism. Upward nudges are capped
   at +{max_up}; downward at -{max_down}. Never exceed these.
4. If the evidence is weak or mixed, return empty dimension_adjustments and confidence "low".
   No correction is better than a wrong one.

Valid dimension names: {", ".join(_DIMENSIONS)}.

Return ONLY valid JSON:
{{
  "overall_tendency": "over_rate" | "under_rate" | "calibrated",
  "dimension_adjustments": {{ "<dimension>": <signed number within [-{max_down}, +{max_up}]> }},
  "confidence": "low" | "medium" | "high",
  "directive": "<one compact sentence the grader can apply, or 'no adjustment'>",
  "caveats": "<selection bias / sample size / no-watch-time notes>"
}}"""


async def generate_calibration_note(platform: str, niche: str) -> dict:
    """Regenerate FROM SCRATCH each time (FIX hole #2 — never stack). Returns the note or
    raises ValueError if below floor (caller falls back to GLOBAL or skips)."""
    # Dormant by default: refuse to synthesize any AI calibration opinion unless the
    # path is explicitly enabled. Raised as ValueError so the admin endpoint reports
    # it as "skipped" alongside below-floor niches.
    if not calibration_enabled():
        raise ValueError(
            "calibration path is disabled (set SURGE_CALIBRATION_ENABLED=1 to enable)"
        )
    cutoff = utc_now_naive() - timedelta(days=RECENCY_WINDOW_DAYS)
    async with AsyncSessionLocal() as db:
        stmt = select(UserAnalysis).where(
            UserAnalysis.platform == platform,
            UserAnalysis.correction_json.is_not(None),
            UserAnalysis.counts_fetched_at >= cutoff,
        )
        # GLOBAL aggregates across every niche; a named niche scopes to itself.
        # Key on canonical_niche (not the raw display niche) so free-text inputs
        # ("fitness") aggregate under their canonical label ("Fitness") and
        # match what load_calibration_note() looks up at grading time.
        if niche != GLOBAL_NICHE:
            stmt = stmt.where(UserAnalysis.canonical_niche == niche)
        rows = (await db.execute(stmt)).scalars().all()

    corrections = []
    for r in rows:
        try:
            c = json.loads(r.correction_json)
        except (ValueError, TypeError):
            continue
        if not isinstance(c, dict):
            continue
        # FIX hole #1: ONLY safe corrections.
        if c.get("safe_to_learn_from") is not True:
            continue
        # FIX hole #2: ignore corrections whose prediction already had a calibration nudge,
        # so we never "correct a correction" into runaway drift.
        if c.get("audited_calibration_version", 0) != 0:
            continue
        # FIX hole #4 (mode): keep only thinking/deep — quick predictions are structurally weak.
        if c.get("mode") not in ("thinking", "deep_thinking"):
            continue
        corrections.append(c)

    if len(corrections) < MIN_CORRECTIONS:
        raise ValueError(
            f"{platform}/{niche}: {len(corrections)} safe corrections, need {MIN_CORRECTIONS}"
        )

    prompt = _build_calibration_prompt(niche, corrections, MIN_PER_DIMENSION, MAX_DOWN, MAX_UP)
    resp = await tracked_generate_content(
        client,
        operation="legacy_calibration_summary",
        model="gemini-2.5-flash",
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction=_GRADING_SYSTEM_INSTRUCTION,
        ),
    )
    note = json.loads(resp.text)
    if not isinstance(note, dict):
        raise ValueError(f"{platform}/{niche}: model returned non-object calibration note")

    # FIX hole #2/#3: clamp every adjustment server-side — never trust the model to respect
    # caps. Drop any adjustment naming a dimension we don't recognise.
    adj = {}
    for dim, v in (note.get("dimension_adjustments") or {}).items():
        if dim not in _DIMENSIONS:
            continue
        try:
            v = float(v)
        except (ValueError, TypeError):
            continue
        adj[dim] = max(-MAX_DOWN, min(MAX_UP, v))
    note["dimension_adjustments"] = adj
    note["sample_count"] = len(corrections)
    return note
