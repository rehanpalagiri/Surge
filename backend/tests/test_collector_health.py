"""P0-B: a failing collector must be observable, not silent.

collector_health() derives an authoritative status from the durable usage_events
ledger + job table (survives restarts), and summarize_run() flags a high-failure
run as an incident (ERROR log + non-OK health)."""
import unittest
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Base, OutcomeCollectionJob, UsageEvent, UserAnalysis
from services.outcome_collection import collector_health, summarize_run
from services.outcomes import utc_now_naive


class CollectorHealthTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _add_fetch_events(self, db, provider, n_ok, n_fail):
        now = utc_now_naive()
        for i in range(n_ok):
            db.add(UsageEvent(operation="fetch_post_metrics", provider=provider,
                              success=True, latency_ms=100, created_at=now))
        for i in range(n_fail):
            db.add(UsageEvent(operation="fetch_post_metrics", provider=provider,
                              success=False, latency_ms=100, error_code="http_429",
                              created_at=now))
        await db.commit()

    async def test_all_failing_reports_failing(self):
        async with self.sessions() as db:
            await self._add_fetch_events(db, "tikwm", n_ok=0, n_fail=8)
            health = await collector_health(db)
        self.assertEqual(health["status"], "failing")
        self.assertEqual(health["fetch_attempts"], 8)
        self.assertEqual(health["fetch_successful"], 0)
        self.assertEqual(health["fetch_failure_ratio"], 1.0)

    async def test_all_success_reports_ok(self):
        async with self.sessions() as db:
            await self._add_fetch_events(db, "tikwm", n_ok=6, n_fail=0)
            health = await collector_health(db)
        self.assertEqual(health["status"], "ok")

    async def test_some_failures_reports_degraded(self):
        async with self.sessions() as db:
            await self._add_fetch_events(db, "rapidapi_instagram", n_ok=9, n_fail=1)
            health = await collector_health(db)
        self.assertEqual(health["status"], "degraded")

    async def test_no_attempts_reports_idle_not_failing(self):
        async with self.sessions() as db:
            health = await collector_health(db)
        # The whole point: "nothing due" must NOT look like an outage.
        self.assertEqual(health["status"], "idle")
        self.assertEqual(health["fetch_attempts"], 0)

    async def test_stale_events_outside_window_are_ignored(self):
        async with self.sessions() as db:
            old = utc_now_naive() - timedelta(days=30)
            db.add(UsageEvent(operation="fetch_post_metrics", provider="tikwm",
                              success=False, latency_ms=100, created_at=old))
            await db.commit()
            health = await collector_health(db, window_days=7)
        self.assertEqual(health["status"], "idle")  # the old failure is out of window

    async def test_job_outcomes_included(self):
        async with self.sessions() as db:
            a = UserAnalysis(filename="v.mp4", niche="Tech", scores_json="{}",
                             verdict="Developing craft", platform="tiktok")
            db.add(a)
            await db.commit()
            await db.refresh(a)
            db.add(OutcomeCollectionJob(analysis_id=a.id, horizon="24h",
                                        due_at=utc_now_naive(), tolerance_hours=6,
                                        status="failed", completed_at=utc_now_naive()))
            await self._add_fetch_events(db, "tikwm", n_ok=0, n_fail=1)
            await db.commit()
            health = await collector_health(db)
        self.assertEqual(health["job_outcomes"].get("failed"), 1)

    def test_summarize_run_flags_incident(self):
        summary = summarize_run({"processed": 4, "results": {
            "complete": 0, "missed": 0, "failed": 4, "pending": 0, "skipped": 0}})
        self.assertTrue(summary["incident"])
        self.assertEqual(summary["failure_ratio"], 1.0)

    def test_summarize_run_clean_run_not_incident(self):
        summary = summarize_run({"processed": 4, "results": {
            "complete": 4, "missed": 0, "failed": 0, "pending": 0, "skipped": 0}})
        self.assertFalse(summary["incident"])


if __name__ == "__main__":
    unittest.main()
