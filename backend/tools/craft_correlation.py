"""Offline craft-vs-outcome correlation — the A1 unlock.

Across ALL users, computes the Pearson and Spearman correlations between each
craft dimension score and the observed like-rate at a FIXED maturity window,
WITH n and a 95% confidence interval for Pearson, plus naive baselines (caption
length, posting hour) for comparison, and the inter-dimension correlation matrix
(P2-A collinearity check).

Honesty rules baked in (do not remove):
  • Only provider-VERIFIED, view-bearing, age-labeled snapshots are used, never
    mixed across maturity windows (same guarantees as services.craft_insights).
  • Every coefficient is reported with n and a 95% CI. Below --min-n the result is
    labeled INSUFFICIENT and must NOT be quoted as a finding.
  • This measures correlation on observed public metrics. It is NOT causation and
    NOT a claim that craft predicts reach. Do not ship a marketing claim from this
    output until n and the interval are stated alongside it.

Usage:
    python -m tools.craft_correlation [--horizon 24h|7d|30d] [--min-n 8] [--json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math

from sqlalchemy import select

from database import AsyncSessionLocal
from models import OutcomeSnapshot, UserAnalysis
from services.craft_insights import (
    DIMENSIONS, DIMENSION_LABELS, HORIZON_ORDER, MIN_VIEWS_FOR_RATE,
    VERIFIED_SOURCES, _craft_scores,
)

# Smallest paired sample we will report a coefficient for without a loud
# INSUFFICIENT label. Mirrors craft_insights.FORECAST_MIN — a Fisher CI on n<8 is
# too wide to distinguish signal from noise, and an r on n<4 has no CI at all.
DEFAULT_MIN_N = 8
COLLINEAR_THRESHOLD = 0.8
_Z95 = 1.959963984540054


def pearson_r(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation, or None when undefined (n<2 or a zero-variance side)."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _rankdata(values: list[float]) -> list[float]:
    """Fractional ranks with ties averaged (competition-style average ranks)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_r(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation = Pearson on ranks; None when undefined."""
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    return pearson_r(_rankdata(xs), _rankdata(ys))


def fisher_ci(r: float | None, n: int, conf_z: float = _Z95) -> tuple[float, float] | None:
    """95% CI for a Pearson r via the Fisher z-transform. None when n<=3 (no CI)."""
    if r is None or n <= 3:
        return None
    r = max(-0.999999, min(0.999999, r))
    z = math.atanh(r)
    se = 1.0 / math.sqrt(n - 3)
    return (math.tanh(z - conf_z * se), math.tanh(z + conf_z * se))


def _round_pair(pair: tuple[float, float] | None) -> list[float] | None:
    return [round(pair[0], 3), round(pair[1], 3)] if pair else None


async def build_correlation_report(db, *, horizon: str | None = None,
                                   min_n: int = DEFAULT_MIN_N) -> dict:
    """Assemble the correlation report from verified, age-matched snapshots."""
    analyses = (await db.execute(
        select(UserAnalysis).where(UserAnalysis.status == "complete")
    )).scalars().all()
    by_id = {a.id: a for a in analyses}
    if not by_id:
        return {"horizon": horizon, "n": 0, "sufficient": False, "min_n": min_n,
                "dimensions": [], "baselines": [],
                "collinearity": {"threshold": COLLINEAR_THRESHOLD, "pairs": [], "flagged": []},
                "note": "No completed analyses.", "caveats": _CAVEATS}

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
        if not s.views or s.views < MIN_VIEWS_FOR_RATE or s.likes is None:
            continue
        key = (s.analysis_id, s.horizon)
        cur = latest.get(key)
        if cur is None or (s.observed_at and cur.observed_at and s.observed_at > cur.observed_at):
            latest[key] = s

    buckets: dict[str, list] = {}
    for (analysis_id, h), s in latest.items():
        scores = _craft_scores(by_id[analysis_id].scores_json)
        if scores is None:
            continue
        buckets.setdefault(h, []).append((by_id[analysis_id], s, scores))

    if not buckets:
        return {"horizon": horizon, "n": 0, "sufficient": False, "min_n": min_n,
                "dimensions": [], "baselines": [],
                "collinearity": {"threshold": COLLINEAR_THRESHOLD, "pairs": [], "flagged": []},
                "note": "No verified, age-labeled snapshots yet.", "caveats": _CAVEATS}

    # Fixed horizon: caller's choice, else the best-populated (tie → more mature).
    if horizon is None:
        horizon = max(buckets, key=lambda h: (len(buckets[h]), HORIZON_ORDER.get(h, 0)))
    rows = buckets.get(horizon, [])

    records = []
    for analysis, snap, scores in rows:
        posted = snap.posted_at or analysis.created_at
        records.append({
            "scores": scores,
            "like_rate": 100.0 * snap.likes / snap.views,
            "caption_len": len(analysis.caption or ""),
            "post_hour": (posted.hour if posted else None),
        })

    n_total = len(records)

    # Per-dimension correlation with observed like-rate.
    dimensions = []
    for dim in DIMENSIONS:
        paired = [(r["scores"][dim], r["like_rate"]) for r in records
                  if r["scores"].get(dim) is not None]
        xs = [p[0] for p in paired]
        ys = [p[1] for p in paired]
        r = pearson_r(xs, ys)
        rho = spearman_r(xs, ys)
        dimensions.append({
            "dimension": dim,
            "label": DIMENSION_LABELS[dim],
            "n": len(paired),
            "r": round(r, 3) if r is not None else None,
            "ci95": _round_pair(fisher_ci(r, len(paired))),
            "spearman": round(rho, 3) if rho is not None else None,
            "insufficient": len(paired) < min_n,
        })

    # Naive baselines: a real finding must beat these. Video duration is not stored,
    # so it's intentionally omitted rather than faked.
    baselines = []
    for name, key in (("caption_length_chars", "caption_len"), ("posting_hour_utc", "post_hour")):
        paired = [(r[key], r["like_rate"]) for r in records if r.get(key) is not None]
        xs = [p[0] for p in paired]
        ys = [p[1] for p in paired]
        r = pearson_r(xs, ys)
        rho = spearman_r(xs, ys)
        baselines.append({
            "baseline": name,
            "n": len(paired),
            "r": round(r, 3) if r is not None else None,
            "ci95": _round_pair(fisher_ci(r, len(paired))),
            "spearman": round(rho, 3) if rho is not None else None,
            "insufficient": len(paired) < min_n,
        })

    collinearity = _collinearity(records, min_n)

    return {
        "horizon": horizon,
        "metric": "observed_like_rate_percent",
        "n": n_total,
        "min_n": min_n,
        "sufficient": n_total >= min_n,
        "dimensions": dimensions,
        "baselines": baselines,
        "collinearity": collinearity,
        "caveats": _CAVEATS,
    }


def _collinearity(records: list[dict], min_n: int) -> dict:
    """Inter-dimension Pearson matrix (P2-A). Flags pairs with |r| >= threshold at
    a justified n — these double-count the same observation in the verdict."""
    pairs = []
    flagged = []
    dims = list(DIMENSIONS)
    for i in range(len(dims)):
        for j in range(i + 1, len(dims)):
            a, b = dims[i], dims[j]
            paired = [(r["scores"][a], r["scores"][b]) for r in records
                      if r["scores"].get(a) is not None and r["scores"].get(b) is not None]
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


_CAVEATS = (
    "Correlation on observed public metrics, NOT causation and NOT a claim that craft "
    "predicts reach. Quote a coefficient only alongside its n and 95% CI. Below min_n "
    "the value is INSUFFICIENT and must not be reported as a finding."
)


def _fmt_ci(ci) -> str:
    return f"[{ci[0]:+.3f}, {ci[1]:+.3f}]" if ci else "(n too small for CI)"


def _print_report(rep: dict) -> None:
    print("=" * 74)
    print("CRAFT ↔ OUTCOME CORRELATION  —  correlation, NOT causation; craft ≠ reach")
    print("=" * 74)
    if rep.get("note"):
        print(f"\n{rep['note']}")
    print(f"\nHorizon: {rep.get('horizon')}   Paired analyses (n): {rep.get('n')}   "
          f"min_n: {rep.get('min_n')}   sufficient: {rep.get('sufficient')}")
    if not rep.get("sufficient"):
        print("\n⚠  INSUFFICIENT DATA — coefficients below are NOT a publishable finding.")

    print("\nPer-dimension vs observed like-rate:")
    print(f"  {'dimension':<20} {'n':>4} {'r':>8} {'rho':>8}   95% CI (Pearson)")
    for d in rep.get("dimensions", []):
        flag = "  INSUFFICIENT" if d["insufficient"] else ""
        rr = f"{d['r']:+.3f}" if d["r"] is not None else "   n/a "
        rho = f"{d['spearman']:+.3f}" if d["spearman"] is not None else "   n/a "
        print(f"  {d['label']:<20} {d['n']:>4} {rr:>8} {rho:>8}   "
              f"{_fmt_ci(d['ci95'])}{flag}")

    print("\nNaive baselines (a real signal must beat these):")
    print(f"  {'baseline':<20} {'n':>4} {'r':>8} {'rho':>8}   95% CI (Pearson)")
    for b in rep.get("baselines", []):
        flag = "  INSUFFICIENT" if b["insufficient"] else ""
        rr = f"{b['r']:+.3f}" if b["r"] is not None else "   n/a "
        rho = f"{b['spearman']:+.3f}" if b["spearman"] is not None else "   n/a "
        print(f"  {b['baseline']:<20} {b['n']:>4} {rr:>8} {rho:>8}   "
              f"{_fmt_ci(b['ci95'])}{flag}")

    col = rep.get("collinearity", {})
    flagged = col.get("flagged", [])
    print(f"\nInter-dimension collinearity (|r| ≥ {col.get('threshold')} at n ≥ {rep.get('min_n')}):")
    if flagged:
        for p in flagged:
            print(f"  ⚑ {p['a']} ~ {p['b']}: r={p['r']:+.3f} (n={p['n']}) — likely double-counted")
        print("  → sharpen the prompt wording or merge the pair; do NOT change verdict math here.")
    else:
        print("  none flagged (either independent, or not enough data to flag).")

    print(f"\n{rep.get('caveats')}")
    print("=" * 74)


async def _amain(args) -> None:
    async with AsyncSessionLocal() as db:
        rep = await build_correlation_report(db, horizon=args.horizon, min_n=args.min_n)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        _print_report(rep)


def main() -> None:
    ap = argparse.ArgumentParser(description="Craft↔outcome correlation (offline).")
    ap.add_argument("--horizon", choices=["24h", "7d", "30d"], default=None,
                    help="fixed maturity window (default: best-populated)")
    ap.add_argument("--min-n", type=int, default=DEFAULT_MIN_N,
                    help=f"minimum paired n before a coefficient is reportable (default {DEFAULT_MIN_N})")
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of the text report")
    asyncio.run(_amain(ap.parse_args()))


if __name__ == "__main__":
    main()
