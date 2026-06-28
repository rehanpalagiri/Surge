"""Creator channel profile (Deep Thinking mode).

Pure function over already-fetched `UserAnalysis` rows so it can be unit-tested
with plain mock objects (no DB). Returns a prompt-ready string, or None when there
isn't enough history (Deep then degrades to Thinking).

Two clearly separated tiers, framed honestly so the scoring AI never mistakes the
system's own past opinions for external validation:

  A. VERIFIED PERFORMANCE — only rows with a real `actual_views` logged. The gold
     anchor for predictions. Needs >= 2 such rows.
  B. SELF-ASSESSMENT TRENDS — derived from past `scores_json` (Surge's own prior
     scoring). Explicitly labelled as internal opinion, used only to flag recurring
     patterns.

`recent_history` deliberately excludes any earlier forecast-like fields so the
AI never anchors to its own guesses.
"""

import json
from statistics import median

# Dimensions present in every user-analysis scores_json (NOT the seed dims).
_DIMENSIONS = [
    ("hook_velocity", "hook velocity"),
    ("cut_frequency", "cut frequency"),
    ("text_scannability", "text scannability"),
    ("curiosity_gap", "curiosity gap"),
    ("audio_visual_sync", "audio-visual sync"),
    ("loop_seamlessness", "ending strength"),
]

MIN_ANALYSES = 2          # below this → no profile at all (Deep → Thinking)
MIN_VERIFIED = 2          # below this → "no verified results" conservative line
MIN_TREND_SAMPLES = 6     # need this many to compute an improving/declining trend
MIN_PATTERN_SAMPLES = 3   # need this many to claim a recurring strength/weakness


def _parse_scores(raw) -> dict:
    """Best-effort parse of a scores_json value into a dict. Never raises."""
    try:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        pass
    return {}


def _as_int(value):
    """Coerce a score to int, or None if it isn't a usable number."""
    if isinstance(value, bool):  # guard: bool is a subclass of int
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def build_channel_profile(analyses: list) -> str | None:
    """analyses: every UserAnalysis row for one (user, platform), any order.

    Returns a prompt block string, or None if there's too little history.
    """
    if not analyses or len(analyses) < MIN_ANALYSES:
        return None

    # Most-recent-first. created_at may be None on freshly-built mocks → treat as
    # oldest so sorting is still stable.
    from datetime import datetime
    rows = sorted(
        analyses,
        key=lambda a: getattr(a, "created_at", None) or datetime.min,
        reverse=True,
    )
    parsed = [(a, _parse_scores(a.scores_json)) for a in rows]
    n = len(parsed)

    # ---- Tier A: verified performance (real actual_views) ----
    verified = [
        (a, s) for (a, s) in parsed
        if getattr(a, "actual_views", None) is not None
    ]
    verified_views = [a.actual_views for (a, s) in verified if a.actual_views is not None]
    verified_likes = [
        a.actual_likes for (a, s) in verified if getattr(a, "actual_likes", None) is not None
    ]

    if len(verified_views) >= MIN_VERIFIED:
        lo, hi = min(verified_views), max(verified_views)
        med = int(median(verified_views))
        line_a = (
            f"  Typical views: {lo:,}–{hi:,} (median {med:,}) across "
            f"{len(verified_views)} post(s) with logged real-world results."
        )
        if verified_likes:
            line_a += f"\n  Typical likes: ~{int(median(verified_likes)):,}."
        line_a += (
            "\n  → Treat this only as historical context. Do not convert it into a "
            "forecast or imply that the new video will land in this range."
        )
        verified_block = "VERIFIED PERFORMANCE (real posted results — the gold anchor):\n" + line_a
    else:
        verified_block = (
            "VERIFIED PERFORMANCE: No verified real-world results logged yet — "
            "calibrate conservatively against global benchmarks, not a personal baseline."
        )

    # ---- Tier B: self-assessment trends (system's own past scoring) ----
    trend_lines = []

    # Recurring strength / weakness across dimensions.
    for key, label in _DIMENSIONS:
        vals = [v for (a, s) in parsed if (v := _as_int(s.get(key))) is not None]
        if len(vals) < MIN_PATTERN_SAMPLES:
            continue
        weak = sum(1 for v in vals if v <= 4)
        strong = sum(1 for v in vals if v >= 7)
        if weak / len(vals) > 0.5:
            trend_lines.append(
                f"  Recurring weakness: {label} (scored ≤4 in {round(100 * weak / len(vals))}% of analyses)."
            )
        elif strong / len(vals) > 0.5:
            trend_lines.append(
                f"  Recurring strength: {label} (scored ≥7 in {round(100 * strong / len(vals))}% of analyses)."
            )

    trends_block = (
        "SELF-ASSESSMENT TRENDS (Surge's own prior scoring of this creator — "
        "internal opinion, NOT external proof):\n" + "\n".join(trend_lines)
        if trend_lines else ""
    )

    # ---- Recent uploads (predictions excluded on purpose) ----
    history_lines = []
    for (a, s) in parsed[:5]:
        views_str = f"{a.actual_views:,} views" if getattr(a, "actual_views", None) is not None else "not logged"
        dims = [(label, v) for (key, label) in _DIMENSIONS if (v := _as_int(s.get(key))) is not None]
        if dims:
            best = max(dims, key=lambda d: d[1])[0]
            worst = min(dims, key=lambda d: d[1])[0]
            dim_str = f" · strongest: {best} · weakest: {worst}"
        else:
            dim_str = ""
        history_lines.append(
            f"  - {a.niche} · actual: {views_str}{dim_str}"
        )
    history_block = (
        "RECENT UPLOADS (most recent first; predictions omitted to avoid anchoring):\n"
        + "\n".join(history_lines)
    )

    blocks = [
        "CREATOR CHANNEL PROFILE (this creator's own history — personalize to it, "
        "but treat Surge's past scores as opinion, not validation):",
        verified_block,
        trends_block,
        history_block,
    ]
    return "\n\n".join(b for b in blocks if b)
