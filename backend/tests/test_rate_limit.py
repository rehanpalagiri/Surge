"""Allowance tests for the monthly free tier + unlimited Pro.

Free = 3 analyses / calendar month (+ earn-by-linking bonus); Pro = unlimited.
Failed (status="error") analyses never consume the allowance; analyses from a
previous month don't count against this month.
"""
import os
import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, User, UserAnalysis
from services.clock import utc_now_naive
from services.rate_limit import get_rate_limit, FREE_MONTHLY_LIMIT, _month_start


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

    async def _user(self, db, subscription_status=None) -> User:
        u = User(
            username=f"u{subscription_status or 'free'}", email=None,
            password_hash="x", subscription_status=subscription_status,
        )
        db.add(u)
        await db.flush()
        return u

    def _analysis(self, user_id, status, created_at, **extra) -> UserAnalysis:
        return UserAnalysis(
            user_id=user_id, platform="tiktok", filename="upload.mp4", niche="Fitness",
            scores_json="{}", verdict="Test", status=status, created_at=created_at, **extra,
        )

    async def test_free_tier_is_three_per_month(self):
        now = utc_now_naive()
        # Anchored to month_start rather than now-N-days: now-N-days would land in
        # the previous calendar month on the 1st/2nd of any month.
        month_start = _month_start(now)
        async with self.Session() as db:
            user = await self._user(db)
            db.add_all([
                self._analysis(user.id, "complete", month_start + timedelta(hours=2)),
                self._analysis(user.id, "complete", month_start + timedelta(hours=1)),
                self._analysis(user.id, "error", now - timedelta(hours=1)),  # excluded
            ])
            await db.commit()
            rl = await get_rate_limit(user, db)
        self.assertEqual(rl["tier"], "free")
        self.assertEqual(rl["base_limit"], FREE_MONTHLY_LIMIT)
        self.assertEqual(rl["used"], 2)          # error row not counted
        self.assertEqual(rl["remaining"], 1)
        self.assertTrue(rl["allowed"])
        self.assertIsNotNone(rl["resets_at"])

    async def test_free_tier_blocks_after_three(self):
        now = utc_now_naive()
        async with self.Session() as db:
            user = await self._user(db)
            db.add_all([self._analysis(user.id, "complete", now - timedelta(hours=i + 1)) for i in range(3)])
            await db.commit()
            rl = await get_rate_limit(user, db)
        self.assertEqual(rl["used"], 3)
        self.assertEqual(rl["remaining"], 0)
        self.assertFalse(rl["allowed"])

    async def test_previous_month_does_not_count(self):
        now = utc_now_naive()
        last_month = _month_start(now) - timedelta(days=2)  # safely in the prior month
        async with self.Session() as db:
            user = await self._user(db)
            db.add_all([
                self._analysis(user.id, "complete", last_month),
                self._analysis(user.id, "complete", last_month),
                self._analysis(user.id, "complete", last_month),
                self._analysis(user.id, "complete", now),  # only this one is this month
            ])
            await db.commit()
            rl = await get_rate_limit(user, db)
        self.assertEqual(rl["used"], 1)
        self.assertTrue(rl["allowed"])

    async def test_pro_is_unlimited(self):
        now = utc_now_naive()
        async with self.Session() as db:
            user = await self._user(db, subscription_status="active")
            db.add_all([self._analysis(user.id, "complete", now - timedelta(hours=i + 1)) for i in range(20)])
            await db.commit()
            rl = await get_rate_limit(user, db)
        self.assertEqual(rl["tier"], "pro")
        self.assertTrue(rl["unlimited"])
        self.assertTrue(rl["allowed"])
        self.assertIsNone(rl["effective_limit"])
        self.assertIsNone(rl["resets_at"])

    async def test_comp_email_gets_unlimited(self):
        # Operator comp allowlist grants Pro with no Stripe — case-insensitive.
        now = utc_now_naive()
        with patch.dict(os.environ, {"COMP_PRO_EMAILS": "owner@surge.com, vip@x.com"}):
            async with self.Session() as db:
                user = User(username="owner", email="Owner@Surge.com", password_hash="x")
                db.add(user)
                await db.flush()
                db.add_all([self._analysis(user.id, "complete", now - timedelta(hours=i + 1)) for i in range(10)])
                await db.commit()
                rl = await get_rate_limit(user, db)
        self.assertEqual(rl["tier"], "pro")
        self.assertTrue(rl["unlimited"])
        self.assertTrue(rl["allowed"])

    async def test_non_comp_email_stays_free(self):
        now = utc_now_naive()
        with patch.dict(os.environ, {"COMP_PRO_EMAILS": "owner@surge.com"}):
            async with self.Session() as db:
                user = User(username="rando", email="rando@x.com", password_hash="x")
                db.add(user)
                await db.flush()
                db.add_all([self._analysis(user.id, "complete", now - timedelta(hours=i + 1)) for i in range(3)])
                await db.commit()
                rl = await get_rate_limit(user, db)
        self.assertEqual(rl["tier"], "free")
        self.assertFalse(rl["allowed"])  # used all 3

    async def test_verified_link_grants_bonus_credit(self):
        now = utc_now_naive()
        # Anchored to month_start rather than now-1-day: now-1-day would land in
        # the previous calendar month on the 1st of any month.
        anchor = _month_start(now) + timedelta(hours=1)
        async with self.Session() as db:
            user = await self._user(db)
            # A verified linked post (url + counts_fetched_at) = +1 to the cap.
            db.add(self._analysis(
                user.id, "complete", anchor,
                video_url="https://www.tiktok.com/@x/video/123",
                counts_fetched_at=anchor,
            ))
            await db.commit()
            rl = await get_rate_limit(user, db)
        self.assertEqual(rl["bonus"], 1)
        self.assertEqual(rl["effective_limit"], FREE_MONTHLY_LIMIT + 1)
        self.assertEqual(rl["used"], 1)
        self.assertEqual(rl["remaining"], FREE_MONTHLY_LIMIT)  # 4 - 1


if __name__ == "__main__":
    unittest.main()
