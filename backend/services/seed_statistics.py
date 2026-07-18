"""Code-first seed-pool statistics — the numeric foundation for niche/trend synthesis.

Extends tools/craft_correlation.py's methodology (Pearson r, Spearman rho, Fisher
z-transform CI, sample-size-justified reportability, inter-dimension collinearity)
from user-analysis outcome data to the admin/harvested seed pool: instead of
correlating craft scores against an observed like-rate, this correlates each
seed's six craft-dimension scores against its code-derived `rating`
(services.seed_analysis.score_outcome — deterministic from real view/like counts,
never an LLM guess).

Every number here is computed in pure Python before any LLM sees it. Downstream
narration (services/seed_insights.py, services/trend_insights.py) is only allowed
to describe what this module already computed — never to "find patterns" in raw
seed text itself. That split is the architecture requirement from updates.md's
"Admin-seed weekly trend synthesis" entry, and mirrors CLAUDE.md's correlation/
causation and sample-size rules.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from tools.craft_correlation import DEFAULT_MIN_N, _round_pair, fisher_ci, pearson_r, spearman_r
from services.craft_insights import DIMENSIONS, DIMENSION_LABELS

# Absolute floor below which a niche's seed pool is noise, not signal. Mirrors
# craft_insights.SPLIT_MIN_PER_SIDE's justification (smallest group where a
# mean/rank isn't defined by a single outlying point) — 3 is the smallest sample
# a "high vs low" split can draw from without one seed silently deciding it.
MIN_SEEDS = 3

# Trend window — a seed posted in this window is "recent"; before it is "established".
# Kept in one place; services/trend_insights.py re-exports these names so existing
# importers (routers/admin.py) don't need to change.
RECENT_WINDOW_DAYS = 30
ESTABLISHED_MIN_DAYS = 30
# Same non-degenerate-group justification as MIN_SEEDS above, applied to the
# "recent" side of the recent-vs-established split.
MIN_RECENT_SEEDS = 3

# Inter-dimension |r| at or above this (with a justified n) flags likely double-counting
# in the verdict — same threshold and reasoning as tools/craft_correlation.py.
COLLINEAR_THRESHOLD = 0.8

# Effect-size tier thresholds on |r|, per Cohen (1988) small/medium/large conventions
# (.1 / .3 / .5) — a literature-grounded cut, not an invented round number. Tier
# assignment is 100% code; the narrating LLM only reads the tier it's handed.
_CRITICAL_R = 0.5
_HIGH_R = 0.3
_STANDARD_R = 0.1
_MAX_CRITICAL = 2

_CAVEATS = (
    "Correlation between a craft dimension score and the seed's code-derived rating "
    "(from real view/like counts via score_outcome), NOT causation and NOT a claim "
    "that craft predicts reach. Below min_n a coefficient is INSUFFICIENT and must "
    "not be treated as a finding."
)


def _dimension_scores(seed) -> dict:
    """Parse a seed's stored craft-dimension scores. Never raises."""
    try:
        data = json.loads(seed.gemini_analysis) if seed.gemini_analysis else {}
    except (ValueError, TypeError):
        return {}
    out = {}
    for d in DIMENSIONS:
        v = data.get(d)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[d] = float(v)
    return out


def _is_content_driven(s) -> bool | None:
    """True for content/mixed drivers. False for distribution. None for old seeds missing the field."""
    try:
        d = json.loads(s.gemini_analysis) if s.gemini_analysis else {}
    except (ValueError, TypeError):
        return None
    drv = d.get("performance_driver")
    if drv is None:
        return None
    return drv in ("content", "mixed")


def select_deconfounded_pool(rated: list, platform: str) -> tuple[list, str | None]:
    """Same de-confounding rule the niche-insight prompt has always applied: TikTok
    pools to content-driven seeds when there are enough of them (isolates craft from
    reach); Instagram (no view counts, driver always "unclear") and thin
    content-driven pools fall back to the full rated set with a low-confidence reason.
    """
    if platform == "instagram":
        return rated, "Instagram: views hidden, rubric not de-confounded by engagement rate."
    content_driven = [s for s in rated if _is_content_driven(s) is True]
    if len(content_driven) >= MIN_SEEDS:
        return content_driven, None
    return rated, "Pre-fix seeds dominate — rubric built on view-anchored data. Re-harvest to de-confound."


def _ref_date(s):
    ref = s.posted_at or s.created_at
    if ref and ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return ref


def _assign_tiers(dimension_stats: list[dict]) -> dict[str, str]:
    """Deterministic, code-only tier assignment from measured |r| — never left to the
    narrating LLM, so a CRITICAL/HIGH/STANDARD/LOW claim always traces to a computed
    correlation. A dimension without a reportable n falls to LOW (no signal, not
    "no effect"). Caps CRITICAL at 2 (the old freeform prompt's convention, kept as a
    prioritization-clarity cap — "these are the top 2", a rank fact, not a
    misstatement of the others' real effect size). Deliberately does NOT force a
    LOW when none arises naturally: a real result where every dimension shows a
    moderate-or-stronger correlation is a legitimate finding, and manufacturing a
    fake "weakest link" by downgrading a genuinely CRITICAL/HIGH dimension to LOW
    would misrepresent its measured effect size to the narrating LLM."""
    reportable = [d for d in dimension_stats if not d["insufficient"] and d["r"] is not None]
    tiers = {d["dimension"]: "LOW" for d in dimension_stats}
    ranked = sorted(reportable, key=lambda d: abs(d["r"]), reverse=True)
    critical = [d for d in ranked if abs(d["r"]) >= _CRITICAL_R][:_MAX_CRITICAL]
    crit_names = {d["dimension"] for d in critical}
    for d in ranked:
        name = d["dimension"]
        if name in crit_names:
            tiers[name] = "CRITICAL"
        elif abs(d["r"]) >= _HIGH_R:
            tiers[name] = "HIGH"
        elif abs(d["r"]) >= _STANDARD_R:
            tiers[name] = "STANDARD"
        else:
            tiers[name] = "LOW"
    return tiers


def _collinearity(records: list[tuple], min_n: int) -> dict:
    """Inter-dimension Pearson matrix across the pool (mirrors
    tools.craft_correlation._collinearity, applied to dimension-vs-dimension instead
    of dimension-vs-outcome)."""
    pairs, flagged = [], []
    dims = list(DIMENSIONS)
    for i in range(len(dims)):
        for j in range(i + 1, len(dims)):
            a, b = dims[i], dims[j]
            paired = [(dv[a], dv[b]) for _, dv in records if a in dv and b in dv]
            xs = [p[0] for p in paired]
            ys = [p[1] for p in paired]
            r = pearson_r(xs, ys)
            entry = {
                "a": a, "b": b, "n": len(paired),
                "r": round(r, 3) if r is not None else None,
                "collinear": (r is not None and abs(r) >= COLLINEAR_THRESHOLD and len(paired) >= min_n),
            }
            pairs.append(entry)
            if entry["collinear"]:
                flagged.append(entry)
    return {"threshold": COLLINEAR_THRESHOLD, "pairs": pairs, "flagged": flagged}


def compute_niche_seed_stats(seeds: list, platform: str, niche: str, *, min_n: int = DEFAULT_MIN_N) -> dict:
    """Validated all-time niche statistics from the seed pool.

    Raises ValueError if there aren't enough rated seeds (caller should skip, not
    fall back to a smaller-sample narrative).
    """
    rated = [s for s in seeds if s.rating is not None]
    if len(rated) < MIN_SEEDS:
        raise ValueError(
            f"Not enough rated seeds for {platform}/{niche} "
            f"({len(rated)} found, {MIN_SEEDS} required). Add more seeds first."
        )

    pool, low_conf_reason = select_deconfounded_pool(rated, platform)
    records = [(s, _dimension_scores(s)) for s in pool]
    records = [(s, dv) for s, dv in records if dv]

    dimension_stats = []
    for dim in DIMENSIONS:
        paired = [(dv[dim], s.rating) for s, dv in records if dim in dv]
        xs = [p[0] for p in paired]
        ys = [p[1] for p in paired]
        r = pearson_r(xs, ys)
        rho = spearman_r(xs, ys)
        n = len(paired)
        high_vals = [dv[dim] for s, dv in records if dim in dv and s.rating >= 6]
        low_vals = [dv[dim] for s, dv in records if dim in dv and s.rating <= 4]
        high_mean = sum(high_vals) / len(high_vals) if high_vals else None
        low_mean = sum(low_vals) / len(low_vals) if low_vals else None
        dimension_stats.append({
            "dimension": dim,
            "label": DIMENSION_LABELS[dim],
            "n": n,
            "r": round(r, 3) if r is not None else None,
            "ci95": _round_pair(fisher_ci(r, n)),
            "spearman": round(rho, 3) if rho is not None else None,
            "insufficient": n < min_n,
            "n_high": len(high_vals),
            "n_low": len(low_vals),
            "high_mean": round(high_mean, 2) if high_mean is not None else None,
            "low_mean": round(low_mean, 2) if low_mean is not None else None,
            "delta": round(high_mean - low_mean, 2) if (high_mean is not None and low_mean is not None) else None,
        })

    tiers = _assign_tiers(dimension_stats)
    for d in dimension_stats:
        d["tier"] = tiers[d["dimension"]]

    return {
        "platform": platform,
        "niche": niche,
        "n_total": len(rated),
        "n_pool": len(pool),
        "n_high": sum(1 for s in pool if s.rating >= 6),
        "n_low": sum(1 for s in pool if s.rating <= 4),
        "min_n": min_n,
        "low_confidence_reason": low_conf_reason,
        "dimensions": dimension_stats,
        "collinearity": _collinearity(records, min_n),
        "caveats": _CAVEATS,
    }


def compute_trend_seed_stats(seeds: list, platform: str, niche: str, *, min_n: int = DEFAULT_MIN_N) -> dict:
    """Validated recent-vs-established delta statistics from the seed pool.

    Raises ValueError if there aren't enough recent seeds. Unlike the niche stats
    above, an "established" side of zero is allowed (early in the product's life)
    — `shift_reportable` flags per-dimension when a delta has a non-degenerate n on
    both sides.
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
            f"{len(recent)} found (need {MIN_RECENT_SEEDS} posted in last {RECENT_WINDOW_DAYS} days)."
        )

    # Parse each seed's JSON once and reuse — DIMENSIONS iterates 6x below, and this
    # loop would otherwise re-run json.loads() per seed per dimension per usage.
    recent_dv = [(s, _dimension_scores(s)) for s in recent]
    established_dv = [(s, _dimension_scores(s)) for s in established]

    dimension_shifts = []
    for dim in DIMENSIONS:
        recent_vals = [dv[dim] for _, dv in recent_dv if dim in dv]
        established_vals = [dv[dim] for _, dv in established_dv if dim in dv]
        recent_mean = sum(recent_vals) / len(recent_vals) if recent_vals else None
        established_mean = sum(established_vals) / len(established_vals) if established_vals else None
        delta = (
            recent_mean - established_mean
            if (recent_mean is not None and established_mean is not None) else None
        )
        paired = [(dv[dim], s.rating) for s, dv in recent_dv if dim in dv]
        xs = [p[0] for p in paired]
        ys = [p[1] for p in paired]
        r = pearson_r(xs, ys)
        dimension_shifts.append({
            "dimension": dim,
            "label": DIMENSION_LABELS[dim],
            "n_recent": len(recent_vals),
            "n_established": len(established_vals),
            "recent_mean": round(recent_mean, 2) if recent_mean is not None else None,
            "established_mean": round(established_mean, 2) if established_mean is not None else None,
            "delta": round(delta, 2) if delta is not None else None,
            "recent_r": round(r, 3) if r is not None else None,
            "recent_r_n": len(paired),
            "recent_r_insufficient": len(paired) < min_n,
            "shift_reportable": len(recent_vals) >= MIN_RECENT_SEEDS and len(established_vals) >= MIN_RECENT_SEEDS,
        })

    return {
        "platform": platform,
        "niche": niche,
        "n_recent": len(recent),
        "n_established": len(established),
        "min_n": min_n,
        "dimensions": dimension_shifts,
        "caveats": _CAVEATS,
    }
