"""Tests for the rolling 5-hour Pro cost-window limiter (services/cost_window.py).

Continuous trailing-window sum over usage_events.estimated_cost_micros, joined to
user_analyses for the user. Same in-memory-SQLite harness and timestamp-seeding
convention as test_rate_limit.py / test_throttle.py — no freezegun.
"""
import os
import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, User, UsageEvent, UserAnalysis
from services.clock import utc_now_naive
from services.cost_window import get_cost_window_status, PRO_COST_WINDOW_HOURS


class CostWindowTest(unittest.IsolatedAsyncioTestCase):
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

    async def _user(self, db) -> User:
        u = User(username="pro-user", email=None, password_hash="x", subscription_status="active")
        db.add(u)
        await db.flush()
        return u

    async def _analysis(self, db, user_id) -> UserAnalysis:
        a = UserAnalysis(
            user_id=user_id, platform="tiktok", filename="upload.mp4", niche="Fitness",
            scores_json="{}", verdict="Test", status="complete",
        )
        db.add(a)
        await db.flush()
        return a

    def _event(self, analysis_id, cost_micros, created_at) -> UsageEvent:
        return UsageEvent(
            analysis_id=analysis_id, operation="video_craft_perception", provider="google_gemini",
            success=True, latency_ms=100, estimated_cost_micros=cost_micros, created_at=created_at,
        )

    async def test_under_budget_allowed(self):
        now = utc_now_naive()
        async with self.Session() as db:
            user = await self._user(db)
            analysis = await self._analysis(db, user.id)
            db.add(self._event(analysis.id, 200_000, now - timedelta(minutes=10)))  # $0.20
            await db.commit()
            status = await get_cost_window_status(user.id, db)
        self.assertTrue(status["allowed"])
        self.assertEqual(status["used_micros"], 200_000)
        self.assertEqual(status["window_hours"], PRO_COST_WINDOW_HOURS)

    async def test_at_or_over_budget_blocks(self):
        now = utc_now_naive()
        async with self.Session() as db:
            user = await self._user(db)
            analysis = await self._analysis(db, user.id)
            db.add(self._event(analysis.id, 600_000, now - timedelta(hours=1)))
            db.add(self._event(analysis.id, 500_000, now - timedelta(minutes=5)))
            await db.commit()
            status = await get_cost_window_status(user.id, db)
        self.assertEqual(status["used_micros"], 1_100_000)
        self.assertFalse(status["allowed"])  # default budget is $1.00 = 1_000_000 micros

    async def test_event_outside_window_excluded(self):
        now = utc_now_naive()
        async with self.Session() as db:
            user = await self._user(db)
            analysis = await self._analysis(db, user.id)
            # Just outside the trailing window — must not count.
            db.add(self._event(
                analysis.id, 5_000_000,
                now - timedelta(hours=PRO_COST_WINDOW_HOURS, minutes=1),
            ))
            # Just inside — must count.
            db.add(self._event(
                analysis.id, 100_000,
                now - timedelta(hours=PRO_COST_WINDOW_HOURS) + timedelta(minutes=1),
            ))
            await db.commit()
            status = await get_cost_window_status(user.id, db)
        self.assertEqual(status["used_micros"], 100_000)
        self.assertTrue(status["allowed"])

    async def test_null_cost_events_ignored(self):
        now = utc_now_naive()
        async with self.Session() as db:
            user = await self._user(db)
            analysis = await self._analysis(db, user.id)
            db.add(self._event(analysis.id, None, now - timedelta(minutes=1)))
            db.add(self._event(analysis.id, 300_000, now - timedelta(minutes=1)))
            await db.commit()
            status = await get_cost_window_status(user.id, db)
        self.assertEqual(status["used_micros"], 300_000)
        self.assertTrue(status["allowed"])

    async def test_events_without_analysis_id_excluded(self):
        now = utc_now_naive()
        async with self.Session() as db:
            user = await self._user(db)
            await self._analysis(db, user.id)  # ensures the user exists w/ an analysis
            db.add(self._event(None, 5_000_000, now - timedelta(minutes=1)))
            await db.commit()
            status = await get_cost_window_status(user.id, db)
        self.assertEqual(status["used_micros"], 0)
        self.assertTrue(status["allowed"])

    async def test_other_users_usage_not_counted(self):
        now = utc_now_naive()
        async with self.Session() as db:
            user = await self._user(db)
            other = User(username="other", email=None, password_hash="x", subscription_status="active")
            db.add(other)
            await db.flush()
            other_analysis = await self._analysis(db, other.id)
            db.add(self._event(other_analysis.id, 5_000_000, now - timedelta(minutes=1)))
            await db.commit()
            status = await get_cost_window_status(user.id, db)
        self.assertEqual(status["used_micros"], 0)
        self.assertTrue(status["allowed"])

    async def test_budget_env_override(self):
        now = utc_now_naive()
        with patch.dict(os.environ, {"PRO_COST_WINDOW_BUDGET_USD": "0.10"}):
            async with self.Session() as db:
                user = await self._user(db)
                analysis = await self._analysis(db, user.id)
                db.add(self._event(analysis.id, 150_000, now - timedelta(minutes=1)))  # $0.15
                await db.commit()
                status = await get_cost_window_status(user.id, db)
        self.assertEqual(status["budget_micros"], 100_000)
        self.assertFalse(status["allowed"])

    async def test_budget_env_zero_falls_back_to_default(self):
        # PRO_COST_WINDOW_BUDGET_USD="0" must NOT mean "block everything" (which a
        # naive `used < 0` check would do for every value of used) — an operator
        # setting "0" almost certainly means "unset", not "lock out all of Pro".
        async with self.Session() as db:
            user = await self._user(db)
            with patch.dict(os.environ, {"PRO_COST_WINDOW_BUDGET_USD": "0"}):
                status = await get_cost_window_status(user.id, db)
        self.assertEqual(status["budget_micros"], 1_000_000)  # falls back to $1.00 default
        self.assertTrue(status["allowed"])

    async def test_budget_env_negative_falls_back_to_default(self):
        async with self.Session() as db:
            user = await self._user(db)
            with patch.dict(os.environ, {"PRO_COST_WINDOW_BUDGET_USD": "-5"}):
                status = await get_cost_window_status(user.id, db)
        self.assertEqual(status["budget_micros"], 1_000_000)
        self.assertTrue(status["allowed"])


if __name__ == "__main__":
    unittest.main()
