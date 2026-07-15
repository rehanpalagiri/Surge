"""Read-only, offline grader score-distribution diagnostic.

This tool is never in the request path. It measures the grader's own score
spread — NOT platform outcomes and NOT grading accuracy.

Usage:
    python -m tools.score_distribution [--json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics

from sqlalchemy import select

from database import AsyncSessionLocal
from models import UserAnalysis
from services.craft_insights import DIMENSIONS, DIMENSION_LABELS, _craft_scores

SCORE_MIN = 0
SCORE_MAX = 10
COMPRESSION_BAND = (5, 7)
COMPRESSION_THRESHOLD = 0.8
BAR_WIDTH = 40


def _valid_scores(scores_json: str) -> dict[str, float | None] | None:
    """Extract a complete, finite 0–10 craft-score row."""
    scores = _craft_scores(scores_json)
    if scores is None:
        return None
    for value in scores.values():
        if value is not None and (
            not math.isfinite(value) or value < SCORE_MIN or value > SCORE_MAX
        ):
            return None
    return scores


def _integer_bucket(value: float) -> int:
    """Round a valid score to its nearest integer bucket, with .5 rounding up."""
    return int(math.floor(value + 0.5))


def _summarize_dimension(dim: str, values: list[float]) -> dict:
    histogram = {str(bucket): 0 for bucket in range(SCORE_MIN, SCORE_MAX + 1)}
    for value in values:
        histogram[str(_integer_bucket(value))] += 1

    n = len(values)
    in_band = sum(COMPRESSION_BAND[0] <= value <= COMPRESSION_BAND[1] for value in values)
    share = in_band / n if n else 0.0
    return {
        "dimension": dim,
        "label": DIMENSION_LABELS[dim],
        "n": n,
        "mean": round(statistics.fmean(values), 3) if values else None,
        "median": round(statistics.median(values), 3) if values else None,
        # These rows are the full stored population being audited, not a sample
        # used to estimate a larger population, so population stdev is appropriate.
        "stdev": round(statistics.pstdev(values), 3) if values else None,
        "histogram": histogram,
        "share_5_7": round(share, 3),
        "compressed": bool(n and share >= COMPRESSION_THRESHOLD),
    }


async def build_score_distribution(db) -> dict:
    """Build a JSON-serializable distribution report from completed analyses."""
    stored = (await db.execute(
        select(UserAnalysis.scores_json).where(UserAnalysis.status == "complete")
    )).scalars().all()

    values_by_dimension = {dim: [] for dim in DIMENSIONS}
    included = 0
    for scores_json in stored:
        scores = _valid_scores(scores_json)
        if scores is None:
            continue
        included += 1
        for dim in DIMENSIONS:
            value = scores[dim]
            if value is not None:
                values_by_dimension[dim].append(value)

    dimensions = [
        _summarize_dimension(dim, values_by_dimension[dim]) for dim in DIMENSIONS
    ] if included else []
    warnings = [
        {
            "dimension": item["dimension"],
            "label": item["label"],
            "share_5_7": item["share_5_7"],
        }
        for item in dimensions if item["compressed"]
    ]

    report = {
        "metric": "grader_score_distribution",
        "score_range": [SCORE_MIN, SCORE_MAX],
        "histogram_bucketing": "nearest_integer",
        "stdev_kind": "population",
        "completed_rows": len(stored),
        "included_rows": included,
        "excluded_unparseable_rows": len(stored) - included,
        "compression_band": list(COMPRESSION_BAND),
        "compression_threshold": COMPRESSION_THRESHOLD,
        "dimensions": dimensions,
        "compression_warnings": warnings,
        "diagnostic_note": (
            "This measures the grader's own score spread, not platform outcomes "
            "or grading accuracy. Compression warnings are diagnostic, not pass/fail."
        ),
    }
    if not included:
        report["note"] = "No completed analyses with parseable craft scores."
    return report


def _bar(count: int, peak: int) -> str:
    if not count or not peak:
        return ""
    length = max(1, round(BAR_WIDTH * count / peak))
    return "#" * length


def _fmt_stat(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"


def _print_report(report: dict) -> None:
    print("=" * 72)
    print("GRADER SCORE DISTRIBUTION — own score spread; NOT outcomes or accuracy")
    print("=" * 72)
    print(
        f"Completed rows: {report['completed_rows']}   "
        f"Included: {report['included_rows']}   "
        f"Excluded (unparseable/invalid): {report['excluded_unparseable_rows']}"
    )

    if report.get("note"):
        print(f"\n{report['note']}")
        print(f"\n{report['diagnostic_note']}")
        print("=" * 72)
        return

    for item in report["dimensions"]:
        print(
            f"\n{item['label']} — n={item['n']}  "
            f"mean={_fmt_stat(item['mean'])}  median={_fmt_stat(item['median'])}  "
            f"stdev(pop)={_fmt_stat(item['stdev'])}  "
            f"share 5–7={item['share_5_7']:.1%}"
        )
        peak = max(item["histogram"].values(), default=0)
        for bucket, count in item["histogram"].items():
            print(f"  {bucket:>2} | {_bar(count, peak):<40} {count}")

    warnings = report["compression_warnings"]
    if warnings:
        flagged = ", ".join(
            f"{item['label']} ({item['share_5_7']:.1%})" for item in warnings
        )
    else:
        flagged = "none"
    print(
        f"\nCompression warning (>= {COMPRESSION_THRESHOLD:.0%} in scores "
        f"{COMPRESSION_BAND[0]}–{COMPRESSION_BAND[1]}): {flagged}. "
        "Diagnostic only — not pass/fail."
    )
    print(f"\n{report['diagnostic_note']}")
    print("=" * 72)


async def _amain(args) -> None:
    async with AsyncSessionLocal() as db:
        report = await build_score_distribution(db)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Grader score-distribution histogram (read-only, offline)."
    )
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of text")
    asyncio.run(_amain(ap.parse_args()))


if __name__ == "__main__":
    main()
