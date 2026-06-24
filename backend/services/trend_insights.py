"""Trend Intelligence — synthesize a "what's changed recently" delta block.

Compares seeds published/harvested in the last 30 days against older seeds to
identify format, topic, and structural shifts. The result is stored in
trend_summaries and injected into the scoring prompt ALONGSIDE niche intelligence
so Gemini knows what's working RIGHT NOW — not just what historically works.

Unlike niche intelligence (which covers all-time patterns), this is only about delta.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from google import genai
from google.genai import types
from services.gemini import _GRADING_SYSTEM_INSTRUCTION
from services.telemetry import tracked_generate_content

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MIN_RECENT_SEEDS = 3
RECENT_WINDOW_DAYS = 30
ESTABLISHED_MIN_DAYS = 30


def _ref_date(s):
    ref = s.posted_at or s.created_at
    if ref and ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return ref


def _age_label(s) -> str:
    now = datetime.now(timezone.utc)
    ref = _ref_date(s)
    if not ref:
        return "age unknown"
    days = (now - ref).days
    if days <= 7:
        return f"{days}d old"
    if days <= 30:
        return f"{days // 7}w old"
    return f"{days // 30}mo old"


def _fmt_seed(s) -> str:
    try:
        data = json.loads(s.gemini_analysis) if s.gemini_analysis else {}
    except (ValueError, TypeError):
        data = {}

    views_str = f"{s.view_count:,} views, " if s.view_count is not None else ""
    parts = [f"[{views_str}{s.like_count:,} likes | Rating {s.rating}/10 | {_age_label(s)}]"]

    for field in ("what_happens", "performance_reason"):
        val = (data.get(field) or "").strip()
        if val:
            parts.append(f"{field}: {val}")

    _DIMS = ("hook_velocity", "cut_frequency", "text_scannability",
             "curiosity_gap", "audio_visual_sync", "loop_seamlessness")
    dim_scores = [f"{d}={data[d]}" for d in _DIMS if data.get(d) is not None]
    if dim_scores:
        parts.append("Dims: " + ", ".join(dim_scores))

    patterns = data.get("patterns") or {}
    if patterns.get("replicate"):
        parts.append("Replicate: " + "; ".join(patterns["replicate"][:3]))

    return "\n".join(parts)


async def generate_trend_insight(seeds: list, platform: str, niche: str) -> str:
    """Synthesize a trend delta from recent vs established seeds for a (platform, niche).

    Raises ValueError if there aren't enough recent seeds or Gemini returns empty.
    """
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=RECENT_WINDOW_DAYS)
    established_cutoff = now - timedelta(days=ESTABLISHED_MIN_DAYS)

    rated = [s for s in seeds if s.rating is not None]
    recent = [s for s in rated if _ref_date(s) and _ref_date(s) >= recent_cutoff]
    established = [s for s in rated if _ref_date(s) and _ref_date(s) < established_cutoff]

    if len(recent) < MIN_RECENT_SEEDS:
        raise ValueError(
            f"Not enough recent seeds for {platform}/{niche} — "
            f"{len(recent)} found (need {MIN_RECENT_SEEDS} posted in last {RECENT_WINDOW_DAYS} days). "
            "Run a Trend Harvest first."
        )

    pname = "TikTok" if platform == "tiktok" else "Instagram Reels"

    recent_high = sorted([s for s in recent if s.rating >= 6], key=lambda s: s.rating, reverse=True)
    recent_low = sorted([s for s in recent if s.rating <= 4], key=lambda s: s.rating)
    est_high = sorted([s for s in established if s.rating >= 6], key=lambda s: s.rating, reverse=True)[:8]

    recent_block = "\n\n".join(_fmt_seed(s) for s in recent_high[:10]) if recent_high else "None yet."
    recent_low_block = "\n\n".join(_fmt_seed(s) for s in recent_low[:5]) if recent_low else "None yet."
    established_block = (
        "\n\n".join(_fmt_seed(s) for s in est_high)
        if est_high else "No established baseline yet — all data is new."
    )

    prompt = f"""You are analyzing trend shifts for a video scoring AI. Your job is to identify what has CHANGED in the {niche} niche on {pname} in the last {RECENT_WINDOW_DAYS} days.

Data summary:
- {len(recent)} videos published in the last {RECENT_WINDOW_DAYS} days ({len(recent_high)} high performers, {len(recent_low)} low performers)
- {len(established)} established videos from before {RECENT_WINDOW_DAYS} days ago (the baseline for comparison)

RECENT HIGH PERFORMERS (last {RECENT_WINDOW_DAYS} days — what is working NOW):
{recent_block}

RECENT LOW PERFORMERS (last {RECENT_WINDOW_DAYS} days — what is failing NOW):
{recent_low_block}

ESTABLISHED HIGH PERFORMERS (older baseline — what WAS working):
{established_block}

Write a TREND INTELLIGENCE REPORT. Focus ONLY on what is DIFFERENT between recent and established performers. A future AI reading this also has the full niche intelligence report (covering all-time patterns) — so do NOT repeat general patterns that appear in both groups. This report is specifically about what has CHANGED.

If there is no meaningful difference between recent and established, say so honestly — do not manufacture trends that are not in the data.

RISING NOW:
What formats, hooks, topics, or structures appear in recent winners that were absent or rare in the established set? Be specific: not "better hooks" but "creators are opening with [specific format] — a technique that rarely appeared in the established baseline." Name actual visual styles, script structures, topics, or pacing choices. Target 250 words. If nothing is rising, say "No clear emerging pattern — recent and established winners use similar approaches."

FADING:
What patterns were common in established winners but absent from recent winners? These may be losing effectiveness on {pname} right now. Be equally specific. Target 250 words. If nothing is clearly fading, say so.

VELOCITY SIGNALS:
Which videos in the recent data are going viral unusually fast (high views relative to their age)? What do the fastest-moving videos have in common — what specific format or hook is driving their velocity? If no velocity outliers exist in the data, say "No velocity outliers in current dataset." Target 200 words.

WHAT TO FLAG RIGHT NOW:
3-5 specific signals a scoring AI should recognize in a new {niche} video on {pname}. Format as actionable flags:
- "FLAG POSITIVE: if the video [specific pattern] — this matches what is going viral this month in this niche"
- "FLAG NEGATIVE: if the creator uses [specific pattern] — this approach dominated 60+ days ago but is underrepresented in recent top performers"
Only write flags grounded in the data above. Do not invent flags from general knowledge. Target 250 words."""

    response = await tracked_generate_content(
        client,
        operation="legacy_trend_insight",
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
            f"Gemini returned empty response for {platform}/{niche} trend synthesis. Try again."
        )
    return text
