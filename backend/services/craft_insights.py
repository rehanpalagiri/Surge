"""Craft-vs-results aggregation for a single creator.

This is the honest answer to "does the review reflect reality?". It grounds the
six craft assessments against the creator's OWN verified, age-matched outcomes —
purely descriptive statistics, explicit sample sizes, never a causal claim and
never the craft model predicting performance from pixels.

Design rules (all enforced below):
  • Only provider-VERIFIED snapshots with a real view count and a labeled
    maturity window (24h / 7d / 30d) are used, and never mixed across windows —
    comparing public metrics at different post ages is invalid.
  • The outcome metric is the observed like rate (likes / views). It is exactly
    that — not quality, not retention, not reach.
  • Per-dimension "patterns" appear only at a justified sample size; below it we
    show the raw table and say so. We never dress up noise as signal.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import OutcomeSnapshot, UserAnalysis

DIMENSIONS = (
    "hook_velocity", "cut_frequency", "text_scannability",
    "curiosity_gap", "audio_visual_sync", "loop_seamlessness",
)
DIMENSION_LABELS = {
    "hook_velocity": "Hook Velocity",
    "cut_frequency": "Cut Frequency",
    "text_scannability": "Text Scannability",
    "curiosity_gap": "Curiosity Gap",
    "audio_visual_sync": "Audio-Visual Sync",
    "loop_seamlessness": "Ending Strength",
}

# A median split is only non-degenerate when each half holds >= 3 observations,
# so per-dimension patterns need >= 6 verified, age-matched posts. (Not a round
# number for its own sake — it's the smallest split where neither side's median
# is a single point that one outlier could define.)
PATTERN_MIN = 6
# An empirical interquartile range is only more than two raw values when the
# middle 50% spans >= 4 points, i.e. >= 8 observations. Below that we don't
# pretend the observed range is a predictive band.
FORECAST_MIN = 8
# Provider sources we treat as verified (vs user-asserted manual entries).
VERIFIED_SOURCES = ("tikwm", "rapidapi", "hikerapi")
HORIZON_ORDER = {"24h": 0, "7d": 1, "30d": 2}


def _quantile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated quantile (q in [0,1]) over a pre-sorted list."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[lo] + frac * (sorted_vals[lo + 1] - sorted_vals[lo])


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    return _quantile(s, 0.5)


def _craft_scores(scores_json: str) -> dict | None:
    """Return the six dimension scores. A dimension the review marked
    not_applicable (deliberate format choice, craft_review_version >= 4)
    comes back as None; any other missing/invalid score voids the row."""
    try:
        data = json.loads(scores_json)
    except (ValueError, TypeError):
        return None
    na = data.get("not_applicable")
    na_keys = set(na) if isinstance(na, dict) else set()
    out = {}
    for key in DIMENSIONS:
        v = data.get(key)
        if v is None and key in na_keys:
            out[key] = None
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        out[key] = float(v)
    return out


async def build_craft_insights(user_id: int, db: AsyncSession) -> dict:
    """Aggregate the creator's craft scores against their verified results.

    Returns a JSON-serializable dict the frontend renders directly. Honest by
    construction: every number is the creator's own observed data, labeled with
    its sample size and maturity window.
    """
    analyses = (await db.execute(
        select(UserAnalysis).where(
            UserAnalysis.user_id == user_id,
            UserAnalysis.status == "complete",
        )
    )).scalars().all()
    total_analyses = len(analyses)
    by_id = {a.id: a for a in analyses}

    empty = {
        "total_analyses": total_analyses,
        "with_verified_outcome": 0,
        "horizon": None,
        "metric": "observed_like_rate",
        "posts": [],
        "patterns": [],
        "pattern_min": PATTERN_MIN,
        "observed_range": {"available": False, "need": FORECAST_MIN, "have": 0},
        "notice": (
            "Patterns are correlations on your own posts at the same post age — "
            "not proof that an edit caused a result, and not a performance guarantee."
        ),
    }
    if not by_id:
        return empty

    # All verified, like-rate-computable, age-labeled snapshots for these analyses.
    snaps = (await db.execute(
        select(OutcomeSnapshot).where(
            OutcomeSnapshot.analysis_id.in_(list(by_id.keys())),
            OutcomeSnapshot.horizon.isnot(None),
            OutcomeSnapshot.views.isnot(None),
            OutcomeSnapshot.likes.isnot(None),
            OutcomeSnapshot.source.in_(VERIFIED_SOURCES),
        )
    )).scalars().all()

    # Keep the latest snapshot per (analysis, horizon) so refreshes don't double-count.
    latest: dict[tuple[int, str], OutcomeSnapshot] = {}
    for s in snaps:
        if not s.views or s.views <= 0 or s.likes is None:
            continue
        key = (s.analysis_id, s.horizon)
        cur = latest.get(key)
        if cur is None or (s.observed_at and cur.observed_at and s.observed_at > cur.observed_at):
            latest[key] = s

    # Bucket by horizon; never mix maturity windows.
    buckets: dict[str, list] = {}
    for (analysis_id, horizon), s in latest.items():
        scores = _craft_scores(by_id[analysis_id].scores_json)
        if scores is None:
            continue
        buckets.setdefault(horizon, []).append((by_id[analysis_id], s, scores))

    if not buckets:
        return empty

    # Use the best-populated window (tie → the more mature one).
    horizon = max(buckets, key=lambda h: (len(buckets[h]), HORIZON_ORDER.get(h, 0)))
    rows = sorted(buckets[horizon], key=lambda r: r[1].observed_at or r[0].created_at, reverse=True)

    posts = []
    like_rates = []
    for analysis, snap, scores in rows:
        like_rate = round(100 * snap.likes / snap.views, 2)  # percent
        like_rates.append(like_rate)
        posts.append({
            "analysis_id": analysis.id,
            "project_name": analysis.project_name,
            "niche": analysis.niche,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
            "scores": scores,
            "views": snap.views,
            "likes": snap.likes,
            "like_rate": like_rate,
        })

    n = len(posts)

    # Per-dimension median split — only when there's enough to be non-degenerate.
    patterns = []
    if n >= PATTERN_MIN:
        for dim in DIMENSIONS:
            # Not-applicable dimensions are unscored on some posts; the
            # per-dimension sample-size floor applies to the scored subset.
            scored = [p for p in posts if p["scores"][dim] is not None]
            if len(scored) < PATTERN_MIN:
                continue
            dim_median = _median([p["scores"][dim] for p in scored])
            high = [p["like_rate"] for p in scored if p["scores"][dim] >= dim_median]
            low = [p["like_rate"] for p in scored if p["scores"][dim] < dim_median]
            # Need both sides populated to compare at all.
            if len(high) < 1 or len(low) < 1:
                continue
            mh, ml = _median(high), _median(low)
            patterns.append({
                "dimension": dim,
                "label": DIMENSION_LABELS[dim],
                "n_high": len(high),
                "n_low": len(low),
                "median_like_rate_high": round(mh, 2),
                "median_like_rate_low": round(ml, 2),
                "delta": round(mh - ml, 2),
                "direction": "higher" if mh > ml else "lower" if mh < ml else "flat",
            })
        # Strongest (by absolute delta) first — that's the most suggestive signal.
        patterns.sort(key=lambda p: abs(p["delta"]), reverse=True)

    # Empirical observed range from the creator's own like rates (no point estimate).
    if n >= FORECAST_MIN:
        s = sorted(like_rates)
        observed_range = {
            "available": True,
            "n": n,
            "horizon": horizon,
            "p25": round(_quantile(s, 0.25), 2),
            "median": round(_quantile(s, 0.5), 2),
            "p75": round(_quantile(s, 0.75), 2),
            "min": round(s[0], 2),
            "max": round(s[-1], 2),
        }
    else:
        # Below the IQR floor we still surface plain descriptive stats —
        # median/min/max of what actually happened — explicitly labeled
        # preliminary. At n=1 all three collapse to the single observation;
        # never percentiles, never a band, so nothing here pretends to be
        # a predictive range.
        s = sorted(like_rates)
        observed_range = {"available": False, "need": FORECAST_MIN, "have": n}
        if n >= 1:
            observed_range["preliminary"] = {
                "n": n,
                "horizon": horizon,
                "median": round(_quantile(s, 0.5), 2),
                "min": round(s[0], 2),
                "max": round(s[-1], 2),
            }

    return {
        "total_analyses": total_analyses,
        "with_verified_outcome": n,
        "horizon": horizon,
        "metric": "observed_like_rate",
        "posts": posts,
        "patterns": patterns,
        "pattern_min": PATTERN_MIN,
        "observed_range": observed_range,
        "notice": empty["notice"],
    }
