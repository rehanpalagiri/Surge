from datetime import timedelta
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Base, OutcomeCollectionJob, OutcomeSnapshot, UserAnalysis
from services.outcome_collection import collect_due_outcomes
from services.outcomes import schedule_outcome_jobs, utc_now_naive


class OutcomeCollectionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_due_job_collects_only_its_real_maturity_window(self):
        posted_at = utc_now_naive() - timedelta(hours=24)
        async with self.sessions() as db:
            analysis = UserAnalysis(
                filename="test.mp4", niche="Tech", scores_json="{}",
                verdict="Developing craft", mode="craft_review", platform="tiktok",
                video_url="https://www.tiktok.com/@creator/video/123",
            )
            db.add(analysis)
            await db.flush()
            await schedule_outcome_jobs(db, analysis_id=analysis.id, posted_at=posted_at)
            await db.commit()

        provider_result = {
            "video_id": "123", "video_url": "https://cdn.test/video.mp4",
            "view_count": 10_000, "like_count": 600, "comment_count": 20,
            "share_count": 10, "save_count": 5, "creator_followers": 2_000,
            "provider_payload_hash": "abc", "posted_at": posted_at,
            "author_handle": "creator",
        }
        with patch("services.outcome_collection.AsyncSessionLocal", self.sessions), patch(
            "services.outcome_collection.fetch_tiktok", AsyncMock(return_value=provider_result)
        ):
            result = await collect_due_outcomes()

        self.assertEqual(result["results"]["complete"], 1)
        async with self.sessions() as db:
            snapshots = (await db.execute(select(OutcomeSnapshot))).scalars().all()
            jobs = (await db.execute(
                select(OutcomeCollectionJob).order_by(OutcomeCollectionJob.due_at)
            )).scalars().all()
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].horizon, "24h")
        self.assertEqual([j.status for j in jobs], ["complete", "pending", "pending"])

    async def test_old_windows_are_marked_missed_not_backfilled(self):
        posted_at = utc_now_naive() - timedelta(days=10)
        async with self.sessions() as db:
            analysis = UserAnalysis(
                filename="old.mp4", niche="Tech", scores_json="{}",
                verdict="Developing craft", mode="craft_review", platform="tiktok",
            )
            db.add(analysis)
            await db.flush()
            await schedule_outcome_jobs(db, analysis_id=analysis.id, posted_at=posted_at)
            await db.commit()
            jobs = (await db.execute(
                select(OutcomeCollectionJob).order_by(OutcomeCollectionJob.due_at)
            )).scalars().all()
        self.assertEqual([j.status for j in jobs], ["missed", "missed", "pending"])


if __name__ == "__main__":
    unittest.main()
