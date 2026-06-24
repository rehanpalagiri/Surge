"""Measured operations report; never substitutes guessed prices for missing cost."""
from __future__ import annotations

from sqlalchemy import case, func, select

from models import AnalysisArtifact, OutcomeCollectionJob, OutcomeSnapshot, UsageEvent


async def build_operations_report(db) -> dict:
    grouped = (await db.execute(
        select(
            UsageEvent.operation,
            UsageEvent.provider,
            func.count(UsageEvent.id),
            func.sum(case((UsageEvent.success.is_(True), 1), else_=0)),
            func.avg(UsageEvent.latency_ms),
            func.avg(UsageEvent.input_tokens),
            func.avg(UsageEvent.output_tokens),
            func.sum(UsageEvent.input_bytes),
            func.sum(UsageEvent.output_bytes),
            func.sum(UsageEvent.estimated_cost_micros),
            func.sum(case((UsageEvent.estimated_cost_micros.is_not(None), 1), else_=0)),
        )
        .group_by(UsageEvent.operation, UsageEvent.provider)
        .order_by(UsageEvent.operation, UsageEvent.provider)
    )).all()

    operations = []
    total_events = 0
    costed_events = 0
    known_cost_micros = 0
    for row in grouped:
        count = int(row[2] or 0)
        costed = int(row[10] or 0)
        total_events += count
        costed_events += costed
        known_cost_micros += int(row[9] or 0)
        operations.append({
            "operation": row[0],
            "provider": row[1],
            "events": count,
            "success_rate": (float(row[3] or 0) / count) if count else None,
            "average_latency_ms": round(float(row[4]), 1) if row[4] is not None else None,
            "average_input_tokens": round(float(row[5]), 1) if row[5] is not None else None,
            "average_output_tokens": round(float(row[6]), 1) if row[6] is not None else None,
            "observed_input_bytes": int(row[7] or 0),
            "observed_output_bytes": int(row[8] or 0),
            "known_cost_micros": int(row[9] or 0) if costed else None,
            "costed_event_coverage": (costed / count) if count else 0,
        })

    async def table_count(model) -> int:
        return int((await db.execute(select(func.count(model.id)))).scalar_one())

    return {
        "operations": operations,
        "totals": {
            "events": total_events,
            "known_cost_micros": known_cost_micros if costed_events else None,
            "costed_event_coverage": (costed_events / total_events) if total_events else 0,
        },
        "storage_row_counts": {
            "analysis_artifacts": await table_count(AnalysisArtifact),
            "outcome_snapshots": await table_count(OutcomeSnapshot),
            "outcome_collection_jobs": await table_count(OutcomeCollectionJob),
            "usage_events": await table_count(UsageEvent),
        },
        "gross_margin": None,
        "gross_margin_status": (
            "Unverified: recognized revenue, conversion, contracted provider pricing, "
            "and allocated variable hosting/storage costs are required."
        ),
    }
