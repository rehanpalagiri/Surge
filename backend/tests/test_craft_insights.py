"""Tests for the craft-vs-verified-results aggregation.

Verifies the honest-by-construction guarantees: only verified, age-matched,
view-bearing snapshots count; maturity windows are never mixed; the observed
like rate is computed correctly; and patterns/forecasts appear only at the
justified sample sizes.
"""
import json
import unittest
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Base, OutcomeSnapshot, UserAnalysis
from services.craft_insights import (
    FORECAST_MIN, PATTERN_MIN, build_craft_insights,
)
from services.outcomes import utc_now_naive

USER = 42


def _scores(hook: float) -> str:
    # Only hook_velocity varies; the rest are held constant so their median
    # split is degenerate (one side empty) and produces no spurious pattern.
    s = {k: 5.0 for k in (
        "cut_frequency", "text_scannability", "curiosity_gap",
        "audio_visual_sync", "loop_seamlessness",
    )}
    s["hook_velocity"] = hook
    return json.dumps(s)


class CraftInsightsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _add_post(self, db, hook, views, likes, *, horizon="7d",
                        source="tikwm", user_id=USER, observed_offset=0):
        a = UserAnalysis(
            user_id=user_id, platform="tiktok", filename="v.mp4",
            niche="Fitness", scores_json=_scores(hook), verdict="Developing craft",
            mode="craft_review", status="complete",
        )
        db.add(a)
        await db.flush()
        if views is not None or likes is not None:
            db.add(OutcomeSnapshot(
                analysis_id=a.id, platform="tiktok", source=source,
                observed_at=utc_now_naive() + timedelta(minutes=observed_offset),
                horizon=horizon, views=views, likes=likes,
                metric_version="observed_response_v1",
            ))
        await db.flush()
        return a

    async def test_empty_when_no_analyses(self):
        async with self.Session() as db:
            out = await build_craft_insights(USER, db)
        self.assertEqual(out["total_analyses"], 0)
        self.assertEqual(out["with_verified_outcome"], 0)
        self.assertFalse(out["forecast"]["available"])

    async def test_like_rate_and_exclusions(self):
        async with self.Session() as db:
            await self._add_post(db, 8, views=1000, likes=120)       # 12.0% verified
            await self._add_post(db, 5, views=2000, likes=100)       # 5.0% verified
            await self._add_post(db, 5, views=500, likes=50, source="manual_unverified")  # excluded
            await self._add_post(db, 5, views=None, likes=300)       # IG-style, no views → excluded
            await self._add_post(db, 5, views=1000, likes=50, horizon=None)  # no window → excluded
            await db.commit()
            out = await build_craft_insights(USER, db)
        self.assertEqual(out["total_analyses"], 5)
        self.assertEqual(out["with_verified_outcome"], 2)  # only the two verified, windowed, view-bearing
        self.assertEqual(out["horizon"], "7d")
        rates = sorted(p["like_rate"] for p in out["posts"])
        self.assertEqual(rates, [5.0, 12.0])

    async def test_never_mixes_horizons(self):
        async with self.Session() as db:
            for i in range(4):
                await self._add_post(db, 6, views=1000, likes=100, horizon="7d")
            for i in range(2):
                await self._add_post(db, 6, views=1000, likes=100, horizon="24h")
            await db.commit()
            out = await build_craft_insights(USER, db)
        # Best-populated window only; the 24h posts must not be folded in.
        self.assertEqual(out["horizon"], "7d")
        self.assertEqual(out["with_verified_outcome"], 4)

    async def test_latest_snapshot_per_analysis_wins(self):
        async with self.Session() as db:
            a = await self._add_post(db, 7, views=1000, likes=50, observed_offset=0)  # 5%
            db.add(OutcomeSnapshot(
                analysis_id=a.id, platform="tiktok", source="tikwm",
                observed_at=utc_now_naive() + timedelta(hours=1),
                horizon="7d", views=1000, likes=90,  # refreshed → 9%
                metric_version="observed_response_v1",
            ))
            await db.commit()
            out = await build_craft_insights(USER, db)
        self.assertEqual(out["with_verified_outcome"], 1)
        self.assertEqual(out["posts"][0]["like_rate"], 9.0)  # the later refresh

    async def test_patterns_gated_by_sample_size(self):
        async with self.Session() as db:
            # 4 verified posts (< PATTERN_MIN) → no patterns yet.
            for likes in (40, 50, 60, 70):
                await self._add_post(db, 6, views=1000, likes=likes)
            await db.commit()
            out = await build_craft_insights(USER, db)
        self.assertLess(out["with_verified_outcome"], PATTERN_MIN)
        self.assertEqual(out["patterns"], [])

    async def test_pattern_detects_hook_signal_and_forecast_unlocks(self):
        async with self.Session() as db:
            # 4 high-hook posts with high like rate, 4 low-hook with low like rate.
            for likes in (50, 60, 70, 80):       # 5–8%
                await self._add_post(db, 8, views=1000, likes=likes)
            for likes in (10, 15, 20, 25):       # 1–2.5%
                await self._add_post(db, 3, views=1000, likes=likes)
            await db.commit()
            out = await build_craft_insights(USER, db)
        self.assertEqual(out["with_verified_outcome"], 8)
        self.assertGreaterEqual(out["with_verified_outcome"], PATTERN_MIN)
        # Hook Velocity should surface as the strongest positive pattern.
        self.assertTrue(out["patterns"])
        hook = next(p for p in out["patterns"] if p["dimension"] == "hook_velocity")
        self.assertEqual(hook["direction"], "higher")
        self.assertGreater(hook["delta"], 0)
        # Constant dimensions must not produce a pattern (one side is empty).
        self.assertFalse(any(p["dimension"] == "cut_frequency" for p in out["patterns"]))
        # Forecast unlocks at >= FORECAST_MIN with an ordered range.
        self.assertGreaterEqual(8, FORECAST_MIN)
        self.assertTrue(out["forecast"]["available"])
        f = out["forecast"]
        self.assertLessEqual(f["min"], f["p25"])
        self.assertLessEqual(f["p25"], f["median"])
        self.assertLessEqual(f["median"], f["p75"])
        self.assertLessEqual(f["p75"], f["max"])

    async def test_other_users_data_excluded(self):
        async with self.Session() as db:
            await self._add_post(db, 8, views=1000, likes=100, user_id=USER)
            await self._add_post(db, 8, views=1000, likes=100, user_id=999)
            await db.commit()
            out = await build_craft_insights(USER, db)
        self.assertEqual(out["total_analyses"], 1)
        self.assertEqual(out["with_verified_outcome"], 1)


if __name__ == "__main__":
    unittest.main()
