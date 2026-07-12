"""P0-C + P2-A: craft↔outcome correlation with n + CI, naive baselines, and the
inter-dimension collinearity matrix. Verified on a throwaway in-memory DB."""
import json
import unittest
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Base, OutcomeSnapshot, UserAnalysis
from services.outcomes import utc_now_naive
from tools.craft_correlation import (
    build_correlation_report, fisher_ci, pearson_r,
)


class PearsonTest(unittest.TestCase):
    def test_perfect_positive(self):
        self.assertAlmostEqual(pearson_r([1, 2, 3, 4], [2, 4, 6, 8]), 1.0, places=6)

    def test_perfect_negative(self):
        self.assertAlmostEqual(pearson_r([1, 2, 3, 4], [8, 6, 4, 2]), -1.0, places=6)

    def test_zero_variance_is_none(self):
        self.assertIsNone(pearson_r([5, 5, 5], [1, 2, 3]))

    def test_too_few_points_is_none(self):
        self.assertIsNone(pearson_r([1], [2]))

    def test_fisher_ci_none_when_n_small(self):
        self.assertIsNone(fisher_ci(0.5, 3))

    def test_fisher_ci_brackets_r(self):
        lo, hi = fisher_ci(0.6, 30)
        self.assertLess(lo, 0.6)
        self.assertGreater(hi, 0.6)
        self.assertGreaterEqual(lo, -1.0)
        self.assertLessEqual(hi, 1.0)


def _scores(hook: float, curiosity: float) -> str:
    return json.dumps({
        "hook_velocity": hook,
        "curiosity_gap": curiosity,       # set == hook in the fixture → collinear
        "cut_frequency": 5.0,             # constant → zero variance → r None
        "text_scannability": 5.0,
        "audio_visual_sync": 5.0,
        "loop_seamlessness": 5.0,
    })


class CorrelationReportTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _seed(self, db, n):
        # like_rate == hook by construction (likes = hook*10, views = 1000), so the
        # hook↔like-rate correlation is a clean +1.0 to check the pipeline end-to-end.
        for i in range(n):
            hook = float(i % 10)
            a = UserAnalysis(
                platform="tiktok", filename="v.mp4", niche="Fitness",
                scores_json=_scores(hook, hook), verdict="Developing craft",
                status="complete", caption="x" * i,
            )
            db.add(a)
            await db.flush()
            db.add(OutcomeSnapshot(
                analysis_id=a.id, platform="tiktok", source="tikwm",
                observed_at=utc_now_naive() + timedelta(minutes=i),
                horizon="7d", views=1000, likes=int(hook * 10),
                metric_version="observed_response_v1",
            ))
        await db.commit()

    async def test_empty_db_is_insufficient(self):
        async with self.Session() as db:
            rep = await build_correlation_report(db)
        self.assertFalse(rep["sufficient"])
        self.assertEqual(rep["n"], 0)
        self.assertIn("note", rep)

    async def test_reports_r_n_ci_and_baselines(self):
        async with self.Session() as db:
            await self._seed(db, 10)
            rep = await build_correlation_report(db, horizon="7d", min_n=8)

        self.assertEqual(rep["horizon"], "7d")
        self.assertEqual(rep["n"], 10)
        self.assertTrue(rep["sufficient"])

        dims = {d["dimension"]: d for d in rep["dimensions"]}
        hook = dims["hook_velocity"]
        self.assertEqual(hook["n"], 10)
        self.assertAlmostEqual(hook["r"], 1.0, places=2)     # perfect by construction
        self.assertIsNotNone(hook["ci95"])                    # n>3 → CI present
        self.assertFalse(hook["insufficient"])
        # A constant dimension has no variance → r is honestly None, not a fake 0.
        self.assertIsNone(dims["cut_frequency"]["r"])

        # Both naive baselines are present, each with n and (for caption) a value.
        names = {b["baseline"] for b in rep["baselines"]}
        self.assertEqual(names, {"caption_length_chars", "posting_hour_utc"})

    async def test_collinearity_flags_duplicated_pair(self):
        async with self.Session() as db:
            await self._seed(db, 10)
            rep = await build_correlation_report(db, horizon="7d", min_n=8)
        flagged = {(p["a"], p["b"]) for p in rep["collinearity"]["flagged"]}
        # hook_velocity and curiosity_gap were set equal → must be flagged collinear.
        self.assertIn(("hook_velocity", "curiosity_gap"), flagged)

    async def test_below_min_n_marked_insufficient(self):
        async with self.Session() as db:
            await self._seed(db, 5)
            rep = await build_correlation_report(db, horizon="7d", min_n=8)
        self.assertFalse(rep["sufficient"])
        self.assertTrue(all(d["insufficient"] for d in rep["dimensions"]))


if __name__ == "__main__":
    unittest.main()
