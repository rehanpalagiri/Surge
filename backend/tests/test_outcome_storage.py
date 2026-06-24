from datetime import timedelta
import unittest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Base, OutcomeSnapshot, UserAnalysis
from services.outcomes import add_outcome_snapshot, utc_now_naive


class OutcomeStorageTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_refreshes_append_immutable_snapshots(self):
        async with self.sessions() as db:
            analysis = UserAnalysis(
                filename="test.mp4",
                niche="Cooking",
                scores_json="{}",
                verdict="Developing craft",
                mode="craft_review",
            )
            db.add(analysis)
            await db.flush()

            posted = utc_now_naive() - timedelta(hours=24)
            first = add_outcome_snapshot(
                db,
                analysis_id=analysis.id,
                platform="tiktok",
                source="tikwm",
                views=1000,
                likes=100,
                posted_at=posted,
            )
            second = add_outcome_snapshot(
                db,
                analysis_id=analysis.id,
                platform="tiktok",
                source="tikwm",
                views=1100,
                likes=105,
                posted_at=posted,
            )
            await db.commit()

            rows = (await db.execute(
                select(OutcomeSnapshot).order_by(OutcomeSnapshot.id)
            )).scalars().all()

            self.assertEqual(len(rows), 2)
            self.assertNotEqual(first.id, second.id)
            self.assertEqual(rows[0].views, 1000)
            self.assertEqual(rows[1].views, 1100)
            self.assertEqual(rows[0].horizon, "24h")


if __name__ == "__main__":
    unittest.main()
