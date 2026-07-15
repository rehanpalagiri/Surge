"""Offline grader score-distribution diagnostic tests."""
import io
import json
import unittest
from contextlib import redirect_stdout

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Base, UserAnalysis
from tools.score_distribution import build_score_distribution, _print_report


def _scores(value: float, *, hook: float | None = None,
            cut: float | None = None) -> str:
    data = {
        "hook_velocity": value if hook is None else hook,
        "cut_frequency": value if cut is None else cut,
        "text_scannability": value,
        "curiosity_gap": value,
        "audio_visual_sync": value,
        "loop_seamlessness": value,
    }
    if cut is None and value == 9:
        data["cut_frequency"] = None
        data["not_applicable"] = {"cut_frequency": "No edits to assess."}
    return json.dumps(data)


class ScoreDistributionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def asyncTearDown(self):
        await self.engine.dispose()

    @staticmethod
    def _analysis(scores_json: str, *, status: str = "complete") -> UserAnalysis:
        return UserAnalysis(
            filename="v.mp4", niche="Fitness", scores_json=scores_json,
            verdict="Developing craft", status=status,
        )

    async def test_empty_database_has_clean_message(self):
        async with self.Session() as db:
            report = await build_score_distribution(db)

        self.assertEqual(report["dimensions"], [])
        self.assertEqual(report["compression_warnings"], [])
        output = io.StringIO()
        with redirect_stdout(output):
            _print_report(report)
        self.assertIn("No completed analyses", output.getvalue())

    async def test_histograms_statistics_na_and_compression_warning(self):
        async with self.Session() as db:
            for score in (5, 6, 7, 5, 9):
                db.add(self._analysis(_scores(score)))
            db.add(self._analysis(_scores(5), status="error"))
            db.add(self._analysis("not json"))
            await db.commit()
            report = await build_score_distribution(db)

        self.assertEqual(report["completed_rows"], 6)
        self.assertEqual(report["included_rows"], 5)
        self.assertEqual(report["excluded_unparseable_rows"], 1)

        dimensions = {item["dimension"]: item for item in report["dimensions"]}
        hook = dimensions["hook_velocity"]
        self.assertEqual(hook["n"], 5)
        self.assertEqual(hook["mean"], 6.4)
        self.assertEqual(hook["median"], 6)
        self.assertEqual(hook["histogram"]["5"], 2)
        self.assertEqual(hook["histogram"]["9"], 1)
        self.assertEqual(hook["share_5_7"], 0.8)
        self.assertTrue(hook["compressed"])

        # The score marked not_applicable is excluded only from this dimension.
        self.assertEqual(dimensions["cut_frequency"]["n"], 4)
        warned = {item["dimension"] for item in report["compression_warnings"]}
        self.assertIn("hook_velocity", warned)

        output = io.StringIO()
        with redirect_stdout(output):
            _print_report(report)
        text = output.getvalue()
        self.assertIn("Hook Velocity — n=5", text)
        self.assertIn("Compression warning", text)
        self.assertIn("Diagnostic only", text)


if __name__ == "__main__":
    unittest.main()
