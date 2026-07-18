"""Niche Intelligence — narrate code-validated seed-pool statistics into a pattern
block that's injected into the live reasoning prompt (services/gemini.py) the same
way the static niche dimension hierarchy already is.

Architecture requirement (updates.md, "Admin-seed weekly trend synthesis" — hard
requirement, not optional): statistics are computed in CODE first
(services/seed_statistics.py, extending tools/craft_correlation.py's methodology —
Pearson r, Fisher CI, sample-size-justified reportability, deterministic tier
assignment). The LLM (Claude Opus 4.8) only narrates those already-validated
numbers into English — it is never handed the raw seed pool and never asked to
"find patterns" itself. That is exactly the unvalidated-correlation risk CLAUDE.md's
correlation/causation rules exist to prevent.
"""

from services import seed_statistics
from services.claude_client import tracked_claude_message

_CORRECTION_CAP = 25  # max corrections fed into the prompt (avoids token bloat)

_NARRATION_SYSTEM = (
    "You are a technical writer producing a niche intelligence report for a video "
    "scoring AI. Your ONLY source of truth is the validated statistics table you are "
    "given — every one of those numbers was computed in code (Pearson correlation, "
    "95% confidence interval, high/low group means, a deterministic effect-size "
    "tier) before this conversation started. Restate and explain those numbers "
    "clearly. Do NOT invent a pattern, technique, causal mechanism, or example that "
    "is not directly derivable from the numbers you were given — you were not shown "
    "any individual video, so you have no basis for one. Where a dimension is marked "
    "insufficient, say so plainly instead of speculating."
)


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


def _fmt_dimension_row(d: dict, min_n: int) -> str:
    if d["insufficient"]:
        return (
            f"{d['label']} ({d['dimension']}): INSUFFICIENT DATA (n={d['n']}, "
            f"need >= {min_n} paired seeds) — tier={d['tier']} by default, no "
            "correlation claim possible."
        )
    if d["r"] is None:
        # n meets the reportable floor but the dimension has zero variance across the
        # pool (e.g. every seed scored the same) — pearson_r is mathematically
        # undefined here, not merely a small sample. Never format None as a number.
        return (
            f"{d['label']} ({d['dimension']}): NO DEFINED CORRELATION (n={d['n']}, "
            f"constant across the pool) — tier={d['tier']} by default."
        )
    ci = f"[{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}]" if d.get("ci95") else "(n too small for CI)"
    means = ""
    if d.get("high_mean") is not None and d.get("low_mean") is not None:
        means = (
            f" High performers (rating>=6, n={d['n_high']}) averaged {d['high_mean']}; "
            f"low performers (rating<=4, n={d['n_low']}) averaged {d['low_mean']} "
            f"(delta={d['delta']:+.2f})."
        )
    return (
        f"{d['label']} ({d['dimension']}): tier={d['tier']}, r={d['r']:+.3f} "
        f"(95% CI {ci}, n={d['n']}), spearman rho={d['spearman']}." + means
    )


def _fmt_stats_table(stats: dict) -> str:
    lines = [_fmt_dimension_row(d, stats["min_n"]) for d in stats["dimensions"]]
    collinear = stats["collinearity"]["flagged"]
    collinear_lines = (
        "\n".join(
            f"  - {p['a']} ~ {p['b']}: r={p['r']:+.3f} (n={p['n']}) — likely double-counted signal"
            for p in collinear
        )
        if collinear else "  none flagged"
    )
    conf_note = (
        f"DATA CONFIDENCE: LOW — {stats['low_confidence_reason']}"
        if stats.get("low_confidence_reason")
        else "DATA CONFIDENCE: adequate — pool was de-confounded to content-driven performers."
    )
    return f"""{conf_note}
Pool: {stats['n_pool']} seeds used ({stats['n_high']} rated >=6, {stats['n_low']} rated <=4), out of {stats['n_total']} total rated seeds.
Reportable-coefficient floor: n >= {stats['min_n']}.

PER-DIMENSION STATISTICS (all computed in code — CRITICAL/HIGH/STANDARD/LOW tiers are a deterministic function of |r|, not an LLM judgment):
{chr(10).join(lines)}

INTER-DIMENSION COLLINEARITY (|r| >= {stats['collinearity']['threshold']} at n >= {stats['min_n']}):
{collinear_lines}

{stats['caveats']}"""


async def generate_niche_insight(
    seeds: list,
    platform: str,
    niche: str,
    corrections: list | None = None,
) -> str:
    """Synthesize all rated seeds for a (platform, niche) pair into a pattern block.

    Computes validated statistics in code first (services.seed_statistics), then has
    Claude Opus 4.8 narrate only those numbers. `corrections` is an optional list of
    safe correction dicts (from UserAnalysis.correction_json) — these are already
    code-filtered structured facts (direction/dimension/confidence), not raw video
    text, so including them doesn't violate the "narrate validated numbers only"
    rule.

    Returns the insight text. Raises ValueError if there aren't enough seeds, or if
    Claude returns nothing usable. Raises RuntimeError if ANTHROPIC_API_KEY isn't
    configured.
    """
    stats = seed_statistics.compute_niche_seed_stats(seeds, platform, niche)
    pname = "TikTok" if platform == "tiktok" else "Instagram Reels"
    stats_block = _fmt_stats_table(stats)

    safe_corrections = (corrections or [])[:_CORRECTION_CAP]
    corrections_block = ""
    if safe_corrections:
        corr_lines = "\n".join(_fmt_correction(c) for c in safe_corrections)
        corrections_block = f"""

REAL-WORLD CALIBRATION CORRECTIONS ({len(safe_corrections)} verified predictions compared to actual outcomes, already
filtered to safe-to-learn-from by code): if corrections show a consistent direction (over_rate/under_rate)
across multiple entries for the same dimension, name the bias explicitly. Only flag a bias if multiple
corrections agree — a signal from one or two entries is noise.
{corr_lines}"""

    prompt = f"""NICHE: {niche}   PLATFORM: {pname}

VALIDATED STATISTICS TABLE (computed in code from {stats['n_total']} rated seeds — this is your only source):
{stats_block}
{corrections_block}

Write the niche intelligence report a video-scoring AI will read before grading new {niche} videos on {pname}.
Structure it as:

DIMENSION WEIGHTS: for each of the six dimensions, state its tier (already computed — do not re-derive
it) and the statistic behind it in one sentence: the r, its 95% CI, n, and the high-vs-low performer gap
where available. If insufficient, say so and do not guess a tier reason.

CALIBRATION SIGNAL: one paragraph summarizing which dimensions this niche's data shows the strongest and
weakest measured relationship to performance, and what a grader should weight more or less heavily as a
result. Cite the actual r values. If corrections were provided, note any consistent bias in a second
paragraph — otherwise state that no calibration corrections were available.

COLLINEARITY NOTE: one sentence on whether any dimension pair is flagged as double-counted signal, and if
so, that a grader should not treat them as fully independent evidence.

CONFIDENCE: restate the DATA CONFIDENCE line from the table and what it means for how firmly a grader
should apply this report.

Do not write sections about hook formats, script structure, editing style, or any other qualitative craft
pattern — you were not shown any individual video and have no basis for such claims. Stay entirely within
what the statistics table supports."""

    return await tracked_claude_message(
        operation="niche_insight_synthesis",
        system=_NARRATION_SYSTEM,
        user_prompt=prompt,
        # Generous headroom: adaptive thinking shares this budget with the answer, and
        # a truncated response is now treated as a hard failure (see claude_client.py)
        # rather than silently stored — better to overprovision than truncate.
        max_tokens=8192,
    )
