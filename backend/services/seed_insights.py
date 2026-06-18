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

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MIN_SEEDS = 3  # below this, patterns are noise not signal


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


async def generate_niche_insight(seeds: list, platform: str, niche: str) -> str:
    """Synthesize all rated seeds for a (platform, niche) pair into a pattern block.

    Returns the insight text. Raises ValueError if there aren't enough seeds.
    Raises _GeminiClientError (re-raised) on quota/key failure.
    """
    rated = [s for s in seeds if s.rating is not None]
    if len(rated) < MIN_SEEDS:
        raise ValueError(
            f"Not enough rated seeds for {platform}/{niche} "
            f"({len(rated)} found, {MIN_SEEDS} required). Add more seeds first."
        )

    high = sorted(
        [s for s in rated if s.rating >= 6],
        key=lambda s: s.rating,
        reverse=True,
    )
    low = sorted(
        [s for s in rated if s.rating <= 4],
        key=lambda s: s.rating,
    )
    mid = [s for s in rated if 4 < s.rating < 6]  # included for context, not pattern-driving

    pname = "TikTok" if platform == "tiktok" else "Instagram Reels"

    high_block = "\n\n".join(_fmt_seed(s) for s in high) if high else "None in dataset."
    low_block = "\n\n".join(_fmt_seed(s) for s in low) if low else "None in dataset."
    mid_note = f"({len(mid)} average performers excluded from pattern analysis — rating 5, neither signal nor noise)" if mid else ""

    prompt = f"""You are building a niche intelligence report for a video scoring AI. This report will be injected into future AI sessions as the sole reference context when scoring new {pname} videos in the {niche} niche. It replaces injecting individual seed examples entirely — so it must be comprehensive, dense, and actionable.

You have data from {len(rated)} real {pname} videos in the {niche} niche: {len(high)} high performers (rating 6–10) and {len(low)} low performers (rating 0–4).
{mid_note}

HIGH PERFORMERS (succeeded on {pname}):
{high_block}

LOW PERFORMERS (failed on {pname}):
{low_block}

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

LOOP SEAMLESSNESS PATTERNS:
How do high performers end their videos — what endings create rewatch loops? What endings appear in low performers that signal scroll-away?

NICHE-SPECIFIC INSIGHTS:
What is unique about the {niche} niche on {pname} that a general scoring AI would miss? What topics, angles, formats, or creator behaviors perform disproportionately well or poorly here specifically?

SCORING CALIBRATION FOR THIS NICHE:
Based on this data, what does a typical {niche} video on {pname} score overall (0–10)? What specific characteristics push a video into the 7–9 range? What guarantees a 2–4?

Target 500 words per section (~4,000 words total). Dense and specific. No padding. Each section must contain enough specific, causal observations that a future AI could apply them without needing to see a single individual seed example."""

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="text/plain",
        ),
    )

    text = (response.text or "").strip()
    if not text:
        raise ValueError(
            f"Gemini returned an empty response for {platform}/{niche} insight generation "
            "(likely a safety filter or empty response). Try again or check the prompt."
        )
    return text
