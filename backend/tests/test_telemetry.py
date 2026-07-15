import unittest
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Base, UsageEvent
import services.telemetry as telemetry


class UsageTelemetryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_record_usage_event_persists_served_model_version(self):
        with patch.object(telemetry, "AsyncSessionLocal", self.sessions):
            await telemetry.record_usage_event(
                operation="video_craft_perception",
                provider="google_gemini",
                model="gemini-2.5-flash",
                model_version="gemini-2.5-flash-served-version",
                success=True,
                latency_ms=25,
            )

        async with self.sessions() as db:
            event = await db.scalar(select(UsageEvent))

        self.assertIsNotNone(event)
        self.assertEqual(event.model_version, "gemini-2.5-flash-served-version")


if __name__ == "__main__":
    unittest.main()
