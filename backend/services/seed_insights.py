"""Niche Intelligence — synthesize all seeds for a (platform, niche) pair into a
single pattern-intelligence block that replaces per-seed injection in the scoring prompt.

Instead of injecting 10–20 individual seed summaries (expensive, repetitive, token-heavy),
we run one Gemini call over the entire seed library for a niche and store the result.
The insight captures what distinguishes HIGH from LOW performers: hook formats, script
structures, pacing patterns, text strategy, audio-sync, loop endings — synthesized into
actionable rules a future AI instance can apply immediately when scoring a new video.
"""

import json
import os

from google import genai
from google.genai import types
from google.genai.errors import ClientError as _GeminiClientError
from services.gemini import _GRADING_SYSTEM_INSTRUCTION
from services.telemetry import tracked_generate_content

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MIN_SEEDS = 3       # below this, patterns are noise not signal
CONFIDENT_FLOOR = 8  # below this many content-driven seeds, force low confidence

_CORRECTION_CAP = 25  # max corrections fed into the prompt (avoids token bloat)


def _is_content_driven(s) -> bool | None:
    """True for content/mixed drivers. False for distribution. None for old seeds missing the field."""
    try:
        d = json.loads(s.gemini_analysis) if s.gemini_analysis else {}
    except (ValueError, TypeError):
        return None
    drv = d.get("performance_driver")
    if drv is None:
        return None  # pre-fix seed — unknown
    return drv in ("content", "mixed")


def _fmt_correction(c: dict) -> str:
    parts = [
        f"direction={c.get('direction') or 'unknown'}",
        f"dimension={c.get('likely_miscalibrated_dimension') or 'overall'}",
        f"confidence={c.get('confidence') or 'unknown'}",
        f"views_at_audit={c.get('audited_at_views') or '?'}",
    ]
    gap = (c.get("gap") or "").strip()
    if gap:
        parts.append(f"gap: {gap}")
    note = (c.get("note") or "").strip()
    if note and note.lower() != "none":
        parts.append(f"note: {note}")
    return " | ".join(parts)


def _fmt_seed(s) -> str:
    """Format a single seed's stored analysis data for the synthesis prompt."""
    try:
        data = json.loads(s.gemini_analysis) if s.gemini_analysis else {}
    except (ValueError, TypeError):
        data = {}

    views_str = f"{s.view_count:,} views, " if s.view_count is not None else ""
    perf = f"{views_str}{s.like_count:,} likes, Rating {s.rating}/10"
    parts = [f"[{perf}]"]

    # Include per-dimension scores when present (new seeds analyzed with updated prompt).
    _DIMS = ("hook_velocity", "cut_frequency", "text_scannability", "curiosity_gap", "audio_visual_sync", "loop_seamlessness")
    dim_scores = [f"{d}={data[d]}" for d in _DIMS if data.get(d) is not None]
    if dim_scores:
        parts.append("Dimension scores: " + ", ".join(dim_scores))

    for field in ("what_happens", "performance_reason", "seed_summary"):
        val = (data.get(field) or "").strip()
        if val:
            parts.append(f"{field}: {val}")

    patterns = data.get("patterns") or {}
    if patterns.get("replicate"):
        parts.append("Replicate: " + "; ".join(patterns["replicate"]))
    if patterns.get("avoid"):
        parts.append("Avoid: " + "; ".join(patterns["avoid"]))

    return "\n".join(parts)


async def generate_niche_insight(
    seeds: list,
    platform: str,
    niche: str,
    corrections: list | None = None,
) -> str:
    """Synthesize all rated seeds for a (platform, niche) pair into a pattern block.

    `corrections` is an optional list of safe correction dicts (from UserAnalysis.correction_json)
    filtered by the caller. When present they are woven into the SCORING CALIBRATION section so
    the synthesis captures both "what works" (seeds) and "where we historically mispredict"
    (real-world outcomes). No minimum floor on corrections — 0 is fine.

    Returns the insight text. Raises ValueError if there aren't enough seeds.
    Raises _GeminiClientError (re-raised) on quota/key failure.
    """
    rated = [s for s in seeds if s.rating is not None]
    if len(rated) < MIN_SEEDS:
        raise ValueError(
            f"Not enough rated seeds for {platform}/{niche} "
            f"({len(rated)} found, {MIN_SEEDS} required). Add more seeds first."
        )

    # Instagram hides view counts — can't de-confound by engagement rate. Key off the
    # platform only: a stray null-view TikTok seed is already handled per-seed (it gets
    # driver "unclear" from score_outcome, so _is_content_driven drops it individually)
    # and must NOT flip the whole TikTok niche out of de-confounding.
    is_instagram = platform == "instagram"

    low_conf_reason = None
    if is_instagram:
        pool = rated
        low_conf_reason = (
            "Instagram: views hidden, rubric not de-confounded by engagement rate."
        )
    else:
        content_driven = [s for s in rated if _is_content_driven(s) is True]
        if len(content_driven) >= MIN_SEEDS:
            pool = content_driven
        else:
            pool = rated
            low_conf_reason = (
                "Pre-fix seeds dominate — rubric built on view-anchored data. "
                "Re-harvest to de-confound."
            )

    high = sorted([s for s in pool if s.rating >= 6], key=lambda s: s.rating, reverse=True)
    low = sorted([s for s in pool if s.rating <= 4], key=lambda s: s.rating)
    mid = [s for s in pool if 4 < s.rating < 6]

    pname = "TikTok" if platform == "tiktok" else "Instagram Reels"

    high_block = "\n\n".join(_fmt_seed(s) for s in high) if high else "None in dataset."
    low_block = "\n\n".join(_fmt_seed(s) for s in low) if low else "None in dataset."
    mid_note = (
        f"({len(mid)} average performers excluded from pattern analysis — rating 5, neither signal nor noise)"
        if mid else ""
    )

    forced_low_conf = low_conf_reason is not None or len(high) < CONFIDENT_FLOOR or len(low) < MIN_SEEDS
    conf_directive = (
        f"DATA CONFIDENCE: LOW. {low_conf_reason or 'Small post-filter sample.'} "
        "State this caveat at the top of your report and avoid asserting hard rules."
        if forced_low_conf
        else "DATA CONFIDENCE: adequate sample of content-driven videos — you may state firm patterns."
    )
    neg_warning = (
        "INSUFFICIENT NEGATIVE EXAMPLES — fewer than 3 low performers. You cannot "
        "reliably define what FAILS; lower confidence accordingly.\n"
        if len(low) < MIN_SEEDS else ""
    )
    # Only tell the model the pool was filtered when it actually was.
    # Transition fallback and Instagram both land on the unfiltered rated pool.
    deconfound_note = (
        "CRITICAL — these HIGH performers were filtered to CONTENT-DRIVEN wins (strong engagement rate), "
        "not reach-driven ones, so their patterns reflect content quality, not audience size.\n"
        if (not is_instagram and low_conf_reason is None)
        else ""
    )

    safe_corrections = (corrections or [])[:_CORRECTION_CAP]
    if safe_corrections:
        corr_lines = "\n\n".join(_fmt_correction(c) for c in safe_corrections)
        corrections_block = f"""
REAL-WORLD CALIBRATION CORRECTIONS ({len(safe_corrections)} verified predictions compared to actual outcomes):
These are cases where this scoring model's predictions were compared to real verified performance data
for {niche} videos on {pname}. Each entry shows the direction of error, which dimension was
miscalibrated, and the confidence of that assessment.

{corr_lines}

Use these in your SCORING CALIBRATION FOR THIS NICHE and DIMENSION WEIGHTS sections: if corrections
show a consistent direction (over_rate/under_rate) across multiple entries for the same dimension,
name the bias explicitly — e.g. "Historical bias: Surge over-rates hook_velocity in this niche —
apply extra scrutiny to hook scores here." Only flag a bias if multiple corrections agree.
"""
    else:
        corrections_block = ""

    prompt = f"""You are building a niche intelligence report for a video scoring AI. This report will be injected into future AI sessions as the sole reference context when scoring new {pname} videos in the {niche} niche. It replaces injecting individual seed examples entirely — so it must be comprehensive, dense, and actionable.

You have data from {len(pool)} real {pname} videos in the {niche} niche: {len(high)} high performers (rating 6–10) and {len(low)} low performers (rating 0–4).
{mid_note}

HIGH PERFORMERS (succeeded on {pname}):
{high_block}

LOW PERFORMERS (failed on {pname}):
{low_block}
{corrections_block}
{conf_directive}
{neg_warning}{deconfound_note}A pattern counts ONLY if it appears consistently across MANY videos in the SAME direction — a pattern from 2–3 videos is noise; discard it. Do not treat a single video's quirk as a rule.

Write the niche intelligence report. Every claim must be grounded in the data above — no generic advice. Be specific and causal: not "good hooks" but "creators open with X which removes the viewer's reason to scroll because Y." Write for an AI reader, not a human.

Structure your report with these exact sections:

HOOK VELOCITY PATTERNS:
What opening structures, formats, and first-2-second approaches characterize high performers vs low performers in this niche? What specific visual or text patterns appear in the first 60 frames of winners? What opening patterns consistently appear in the losers?

CURIOSITY GAP PATTERNS:
What script architectures, open loop styles, and information-reveal structures dominate high performers? What specific phrases, claims, or formats create the open loop? What script failures (introductions, context-setting, slow reveals) appear in low performers?

CUT FREQUENCY PATTERNS:
What pacing rhythms, cut frequencies, and shot lengths characterize winners vs losers in this niche? Are there niche-specific pacing norms (e.g., does this niche tolerate longer takes than average)? What static-hold durations or pacing failures appear in low performers?

TEXT SCANNABILITY PATTERNS:
What on-screen text strategies (timing, position, size, style, density) appear in high performers? Is this niche particularly dependent on mute-watchability? What text failures or absences appear in low performers?

AUDIO-VISUAL SYNC PATTERNS:
What audio strategies, sync approaches, music choices, or sound design patterns characterize winners? Are there niche-specific audio norms? What audio failures appear in low performers?

ENDING STRENGTH PATTERNS:
How do high performers end their videos — what endings earn the finish (payoff, CTA, or a clean loop) and create rewatch/share impulse? What endings appear in low performers that signal scroll-away?

NICHE-SPECIFIC INSIGHTS:
What is unique about the {niche} niche on {pname} that a general scoring AI would miss? What topics, angles, formats, or creator behaviors perform disproportionately well or poorly here specifically?

SCORING CALIBRATION FOR THIS NICHE:
Based on this data, what does a typical {niche} video on {pname} score overall (0–10)? What specific characteristics push a video into the 7–9 range? What guarantees a 2–4?

DIMENSION WEIGHTS:
Based ONLY on what you observe in the data above — not on general assumptions — assign each of the 6 scoring dimensions to exactly one tier. A tier is earned by what the data shows.

Tier definitions:
- CRITICAL: Failing this dimension (score ≤ 3) alone makes viral success impossible regardless of other strengths. High performers almost universally excel here; low performers almost universally fail here.
- HIGH: Strongly shapes overall_score. Clear separation between high and low performers. A low score here significantly drags the overall even when other dimensions are strong.
- STANDARD: Normal weight. Contributes proportionally. Some differentiation between high and low performers but not decisive.
- LOW: Minimal weight. A low score here barely affects overall_score when other dimensions are strong. High and low performers show little consistent difference here.

Rules:
- At most 2 dimensions may be CRITICAL.
- At least 1 dimension must be LOW.
- All 6 dimensions must be assigned. The percentages must sum to 100%.

Format this section EXACTLY as follows (preserve the arrows and tier labels):
hook_velocity → [CRITICAL|HIGH|STANDARD|LOW] (~X%): [one sentence citing specific counts from the data, e.g. "11 of 14 high performers opened with movement or text in the first 2 seconds vs 1 of 8 low performers"]
cut_frequency → [CRITICAL|HIGH|STANDARD|LOW] (~X%): [data-grounded rationale]
text_scannability → [CRITICAL|HIGH|STANDARD|LOW] (~X%): [data-grounded rationale]
curiosity_gap → [CRITICAL|HIGH|STANDARD|LOW] (~X%): [data-grounded rationale]
audio_visual_sync → [CRITICAL|HIGH|STANDARD|LOW] (~X%): [data-grounded rationale]
loop_seamlessness → [CRITICAL|HIGH|STANDARD|LOW] (~X%): [data-grounded rationale]

Target 500 words per section for the pattern sections (~4,000 words total). Dense and specific. No padding. Each section must contain enough specific, causal observations that a future AI could apply them without needing to see a single individual seed example."""

    response = await tracked_generate_content(
        client,
        operation="legacy_niche_insight",
        model="gemini-2.5-flash",
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=_GRADING_SYSTEM_INSTRUCTION,
        ),
    )

    text = (response.text or "").strip()
    if not text:
        raise ValueError(
            f"Gemini returned an empty response for {platform}/{niche} insight generation "
            "(likely a safety filter or empty response). Try again or check the prompt."
        )
    if "DIMENSION WEIGHTS:" not in text:
        raise ValueError(
            f"Gemini insight for {platform}/{niche} is missing the DIMENSION WEIGHTS section. "
            "The response may have been truncated or the model skipped the section. "
            "Try regenerating."
        )
    return text
