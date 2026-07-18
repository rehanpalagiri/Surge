"""Trend Intelligence — narrate code-validated recent-vs-established seed-pool
statistics into a "what's changed recently" delta block.

Same architecture requirement as services/seed_insights.py: statistics are computed
in CODE first (services/seed_statistics.py), and Claude Opus 4.8 only narrates
those already-validated numbers — never a freeform read of raw seed text. See
seed_insights.py's module docstring for the full rationale.

Unlike niche intelligence (all-time patterns), this is only about the delta between
seeds posted in the last RECENT_WINDOW_DAYS and older "established" seeds.
"""

from services import seed_statistics
from services.claude_client import tracked_claude_message

# Re-exported so existing importers (routers/admin.py) don't need to change.
RECENT_WINDOW_DAYS = seed_statistics.RECENT_WINDOW_DAYS
ESTABLISHED_MIN_DAYS = seed_statistics.ESTABLISHED_MIN_DAYS
MIN_RECENT_SEEDS = seed_statistics.MIN_RECENT_SEEDS
_ref_date = seed_statistics._ref_date


def count_recent_established(seeds: list) -> tuple[int, int]:
    """(recent_count, established_count) for a seed list, using the same cutoffs
    generate_trend_insight's compute_trend_seed_stats applies. Shared by every
    caller that persists these counts alongside the trend text (routers/admin.py's
    manual trigger, services/niche_synthesis.py's weekly run) so the stored counts
    can't drift from what the narration was actually computed over."""
    from datetime import datetime, timedelta, timezone
    now_utc = datetime.now(timezone.utc)
    recent_cutoff = now_utc - timedelta(days=RECENT_WINDOW_DAYS)
    established_cutoff = now_utc - timedelta(days=ESTABLISHED_MIN_DAYS)
    recent = sum(1 for s in seeds if _ref_date(s) and _ref_date(s) >= recent_cutoff)
    established = sum(1 for s in seeds if _ref_date(s) and _ref_date(s) < established_cutoff)
    return recent, established

_NARRATION_SYSTEM = (
    "You are a technical writer producing a trend-delta report for a video scoring "
    "AI. Your ONLY source of truth is the validated recent-vs-established statistics "
    "table you are given — every number was computed in code before this "
    "conversation started. Restate and explain those numbers. Do NOT invent a "
    "format, hook, topic, or technique that is not directly derivable from the "
    "numbers — you were not shown any individual video. Where a shift is not "
    "reportable (too few seeds on one side), say so plainly instead of speculating "
    "about what might be changing."
)


def _fmt_shift_row(d: dict) -> str:
    if not d["shift_reportable"]:
        return (
            f"{d['label']} ({d['dimension']}): NOT REPORTABLE (n_recent={d['n_recent']}, "
            f"n_established={d['n_established']}, need >= {seed_statistics.MIN_RECENT_SEEDS} on each side)."
        )
    delta = d["delta"]
    direction = "up" if (delta or 0) > 0 else "down" if (delta or 0) < 0 else "flat"
    r_note = (
        f" Recent-window correlation with rating: r={d['recent_r']:+.3f} (n={d['recent_r_n']})"
        + (" — insufficient n for confidence." if d["recent_r_insufficient"] else ".")
        if d["recent_r"] is not None else ""
    )
    return (
        f"{d['label']} ({d['dimension']}): recent mean {d['recent_mean']} (n={d['n_recent']}) vs "
        f"established mean {d['established_mean']} (n={d['n_established']}) — delta {delta:+.2f} ({direction})."
        f"{r_note}"
    )


def _fmt_trend_table(stats: dict) -> str:
    lines = [_fmt_shift_row(d) for d in stats["dimensions"]]
    return f"""Recent window: last {seed_statistics.RECENT_WINDOW_DAYS} days ({stats['n_recent']} rated seeds).
Established baseline: older than {seed_statistics.ESTABLISHED_MIN_DAYS} days ({stats['n_established']} rated seeds).

PER-DIMENSION RECENT-VS-ESTABLISHED SHIFT (computed in code):
{chr(10).join(lines)}

{stats['caveats']}"""


async def generate_trend_insight(seeds: list, platform: str, niche: str) -> str:
    """Synthesize a trend delta from recent vs established seeds for a (platform, niche).

    Computes validated statistics in code first (services.seed_statistics), then has
    Claude Opus 4.8 narrate only those numbers.

    Raises ValueError if there aren't enough recent seeds. Raises RuntimeError if
    ANTHROPIC_API_KEY isn't configured.
    """
    stats = seed_statistics.compute_trend_seed_stats(seeds, platform, niche)
    pname = "TikTok" if platform == "tiktok" else "Instagram Reels"
    stats_block = _fmt_trend_table(stats)

    prompt = f"""NICHE: {niche}   PLATFORM: {pname}

VALIDATED RECENT-VS-ESTABLISHED STATISTICS (computed in code — this is your only source):
{stats_block}

Write a TREND INTELLIGENCE REPORT a video-scoring AI will read alongside the all-time niche intelligence
report. Focus ONLY on the deltas in the table above — do not repeat general patterns, and do not describe
what any specific video does.

Structure it as:

WHAT SHIFTED: for each reportable dimension, one sentence stating the direction and size of the shift and
whether the recent-window correlation with rating still holds. If a dimension is not reportable, say so.

WHAT TO FLAG RIGHT NOW: up to 3 sentences translating the reportable shifts into what a grader should watch
for — phrased as "recent seeds in this niche score higher/lower on X than established ones," never as a
description of specific creative technique you were not shown.

If nothing is reportable, say plainly that there isn't enough recent data yet to identify a trend — do not
manufacture one."""

    return await tracked_claude_message(
        operation="trend_insight_synthesis",
        system=_NARRATION_SYSTEM,
        user_prompt=prompt,
        # Generous headroom: adaptive thinking shares this budget with the answer, and
        # a truncated response is now treated as a hard failure (see claude_client.py)
        # rather than silently stored — better to overprovision than truncate.
        max_tokens=4096,
    )
