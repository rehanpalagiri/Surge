"""Regression test: POST /api/admin/outcomes/collect-due must read `limit` from
the JSON body.

It used to be a bare query param, so the scheduler's `-d '{"limit": 100}'` body
was silently ignored and every run collected only the 25-job default — surplus
due jobs aged out past tolerance and were lost. These tests pin the body binding
(and the admin guard).
"""
import unittest
from datetime import timedelta
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from models import Base, OutcomeCollectionJob, UserAnalysis
from services.outcomes import schedule_outcome_jobs, utc_now_naive

ADMIN = {"X-Admin-Password": "viraliq-admin"}  # check_admin's dev default


class CollectDueEndpointTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        # collect_due_outcomes uses AsyncSessionLocal directly — point it at the
        # in-memory DB. Patches stay active for the whole test via addCleanup.
        p1 = patch("services.outcome_collection.AsyncSessionLocal", self.Session)
        p1.start(); self.addCleanup(p1.stop)
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def _seed_due_jobs(self, n: int):
        """Create n analyses posted ~25h ago (no video_url) -> n DUE 24h jobs.
        No video_url means _collect_job fails fast with no provider network call,
        but the job is still selected/processed, so `processed` reflects the limit.
        """
        posted_at = utc_now_naive() - timedelta(hours=25)
        async with self.Session() as db:
            for i in range(n):
                a = UserAnalysis(
                    filename=f"v{i}.mp4", niche="Tech", scores_json="{}",
                    verdict="Developing craft", mode="craft_review", platform="tiktok",
                )
                db.add(a)
                await db.flush()
                await schedule_outcome_jobs(db, analysis_id=a.id, posted_at=posted_at)
            await db.commit()
            due = [j for j in (await db.execute(select(OutcomeCollectionJob))).scalars().all()
                   if j.status == "pending" and j.due_at <= utc_now_naive()]
        return len(due)

    async def test_limit_is_read_from_body(self):
        due = await self._seed_due_jobs(5)
        self.assertEqual(due, 5, "setup should produce 5 due 24h jobs")

        r = await self.client.post("/api/admin/outcomes/collect-due", json={"limit": 2}, headers=ADMIN)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["processed"], 2, "body limit=2 must cap the batch at 2")

    async def test_default_processes_full_batch_when_no_body(self):
        await self._seed_due_jobs(5)
        r = await self.client.post("/api/admin/outcomes/collect-due", headers=ADMIN)
        self.assertEqual(r.status_code, 200, r.text)
        # Default limit is 100, so all 5 due jobs are processed in one run.
        self.assertEqual(r.json()["processed"], 5)

    async def test_requires_admin_password(self):
        r = await self.client.post("/api/admin/outcomes/collect-due", json={"limit": 1})
        self.assertEqual(r.status_code, 401)
        bad = await self.client.post(
            "/api/admin/outcomes/collect-due", json={"limit": 1},
            headers={"X-Admin-Password": "wrong"},
        )
        self.assertEqual(bad.status_code, 401)


if __name__ == "__main__":
    unittest.main()
