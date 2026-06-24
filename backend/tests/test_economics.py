import unittest

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Base, UsageEvent
from services.economics import build_operations_report


class EconomicsReportTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_report_keeps_unknown_cost_and_margin_explicit(self):
        async with self.sessions() as db:
            db.add_all([
                UsageEvent(operation="video_craft_analysis", provider="gemini", success=True, latency_ms=1000),
                UsageEvent(operation="video_craft_analysis", provider="gemini", success=False, latency_ms=3000),
            ])
            await db.commit()
            report = await build_operations_report(db)

        operation = report["operations"][0]
        self.assertEqual(operation["events"], 2)
        self.assertEqual(operation["success_rate"], 0.5)
        self.assertEqual(operation["average_latency_ms"], 2000.0)
        self.assertIsNone(operation["known_cost_micros"])
        self.assertEqual(report["totals"]["costed_event_coverage"], 0)
        self.assertIsNone(report["gross_margin"])


if __name__ == "__main__":
    unittest.main()
