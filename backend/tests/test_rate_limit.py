import unittest
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, UserAnalysis
from services.rate_limit import get_rate_limit


class RateLimitTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _analysis(self, status: str | None, created_at: datetime) -> UserAnalysis:
        return UserAnalysis(
            user_id=1,
            platform="tiktok",
            filename="upload.mp4",
            niche="Fitness",
            scores_json="{}",
            verdict="Test",
            status=status,
            created_at=created_at,
        )

    async def test_error_rows_do_not_consume_limit_or_reset_window(self):
        now = datetime.utcnow()
        async with self.Session() as db:
            db.add_all([
                await self._analysis("error", now - timedelta(minutes=170)),
                await self._analysis("complete", now - timedelta(minutes=60)),
                await self._analysis("processing", now - timedelta(minutes=40)),
                await self._analysis("pending", now - timedelta(minutes=20)),
                await self._analysis("complete", now - timedelta(hours=4)),
            ])
            await db.commit()

            result = await get_rate_limit(1, db)

        self.assertEqual(result["used"], 3)
        self.assertEqual(result["remaining"], 7)
        self.assertIsNotNone(result["resets_at"])
        self.assertTrue(
            result["resets_at"].startswith((now - timedelta(minutes=60) + timedelta(hours=3)).isoformat()[:19])
        )

    async def test_legacy_null_status_counts_as_consumed(self):
        now = datetime.utcnow()
        async with self.Session() as db:
            db.add(await self._analysis(None, now - timedelta(minutes=10)))
            await db.commit()

            result = await get_rate_limit(1, db)

        self.assertEqual(result["used"], 1)


if __name__ == "__main__":
    unittest.main()
