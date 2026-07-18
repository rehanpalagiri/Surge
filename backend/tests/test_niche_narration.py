"""Tests for services/seed_insights.py and services/trend_insights.py — the
narration layer. Verifies the hard architecture requirement from updates.md:
statistics are computed in code first (services/seed_statistics.py) and the LLM
call only ever receives the validated numbers, never a raw seed dump.
"""
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import services.seed_insights as seed_insights
import services.trend_insights as trend_insights


def _seed(rating, dims: dict, *, driver="content", days_old=200,
          what_happens="a very specific unique raw description xyzzy123"):
    payload = dict(dims)
    payload["performance_driver"] = driver
    payload["what_happens"] = what_happens
    payload["performance_reason"] = "raw qualitative reasoning text should never leak"
    return SimpleNamespace(
        rating=rating,
        gemini_analysis=json.dumps(payload),
        posted_at=datetime.now(timezone.utc) - timedelta(days=days_old),
        created_at=datetime.now(timezone.utc) - timedelta(days=days_old),
    )


class GenerateNicheInsightTest(unittest.IsolatedAsyncioTestCase):
    async def test_raises_before_calling_claude_when_too_few_seeds(self):
        claude_mock = AsyncMock(side_effect=AssertionError("Claude must not be called"))
        with patch.object(seed_insights, "tracked_claude_message", new=claude_mock):
            with self.assertRaises(ValueError):
                await seed_insights.generate_niche_insight([_seed(7, {"hook_velocity": 7})], "tiktok", "Fitness")
        claude_mock.assert_not_awaited()

    async def test_prompt_carries_computed_numbers_not_raw_seed_text(self):
        ratings = [9, 8, 7, 6, 5, 4, 3, 2, 9, 3]
        seeds = [_seed(r, {"hook_velocity": r, "curiosity_gap": 10 - r}) for r in ratings]

        claude_mock = AsyncMock(return_value="narrated report")
        with patch.object(seed_insights, "tracked_claude_message", new=claude_mock):
            result = await seed_insights.generate_niche_insight(seeds, "tiktok", "Fitness")

        self.assertEqual(result, "narrated report")
        claude_mock.assert_awaited_once()
        prompt = claude_mock.await_args.kwargs["user_prompt"]

        # Validated numbers must be present.
        self.assertIn("hook_velocity", prompt)
        self.assertIn("tier=CRITICAL", prompt)
        self.assertIn("r=+1.000", prompt)

        # Raw per-video text must never reach the model — that's exactly the
        # "freeform find patterns over raw seed data" risk the doc forbids.
        self.assertNotIn("xyzzy123", prompt)
        self.assertNotIn("raw qualitative reasoning text should never leak", prompt)

    async def test_zero_variance_dimension_does_not_crash_prompt_building(self):
        # cut_frequency is a constant 5 across every seed (n=10 >= the reportable
        # floor, but pearson_r is mathematically undefined for zero variance) — this
        # must format as "no defined correlation", never crash trying to apply a
        # numeric format spec to r=None.
        ratings = [9, 8, 7, 6, 5, 4, 3, 2, 9, 3]
        seeds = [_seed(r, {"hook_velocity": r, "cut_frequency": 5}) for r in ratings]

        claude_mock = AsyncMock(return_value="narrated report")
        with patch.object(seed_insights, "tracked_claude_message", new=claude_mock):
            result = await seed_insights.generate_niche_insight(seeds, "tiktok", "Fitness")

        self.assertEqual(result, "narrated report")
        prompt = claude_mock.await_args.kwargs["user_prompt"]
        self.assertIn("NO DEFINED CORRELATION", prompt)

    async def test_corrections_are_included_as_structured_facts(self):
        seeds = [_seed(r, {"hook_velocity": r}) for r in [9, 8, 7, 6, 5, 4, 3]]
        corrections = [{
            "direction": "over_rate", "likely_miscalibrated_dimension": "hook_velocity",
            "confidence": "high", "audited_at_views": 50000, "gap": "predicted low, actual high",
        }]
        claude_mock = AsyncMock(return_value="narrated report")
        with patch.object(seed_insights, "tracked_claude_message", new=claude_mock):
            await seed_insights.generate_niche_insight(seeds, "tiktok", "Fitness", corrections=corrections)
        prompt = claude_mock.await_args.kwargs["user_prompt"]
        self.assertIn("over_rate", prompt)
        self.assertIn("CALIBRATION CORRECTIONS", prompt)

    async def test_raises_when_claude_returns_nothing(self):
        seeds = [_seed(r, {"hook_velocity": r}) for r in [9, 8, 7, 6, 5, 4, 3]]
        claude_mock = AsyncMock(side_effect=ValueError("Claude returned an empty response for operation=x"))
        with patch.object(seed_insights, "tracked_claude_message", new=claude_mock):
            with self.assertRaises(ValueError):
                await seed_insights.generate_niche_insight(seeds, "tiktok", "Fitness")


class GenerateTrendInsightTest(unittest.IsolatedAsyncioTestCase):
    async def test_raises_before_calling_claude_when_too_few_recent_seeds(self):
        claude_mock = AsyncMock(side_effect=AssertionError("Claude must not be called"))
        seeds = [_seed(7, {"hook_velocity": 7}, days_old=200) for _ in range(5)]  # all established
        with patch.object(trend_insights, "tracked_claude_message", new=claude_mock):
            with self.assertRaises(ValueError):
                await trend_insights.generate_trend_insight(seeds, "tiktok", "Fitness")
        claude_mock.assert_not_awaited()

    async def test_prompt_carries_computed_shift_not_raw_seed_text(self):
        recent = [_seed(9, {"hook_velocity": 9}, days_old=5, what_happens="recent-only-marker-abc") for _ in range(4)]
        established = [_seed(4, {"hook_velocity": 4}, days_old=200, what_happens="established-only-marker-xyz") for _ in range(4)]

        claude_mock = AsyncMock(return_value="trend report")
        with patch.object(trend_insights, "tracked_claude_message", new=claude_mock):
            result = await trend_insights.generate_trend_insight(recent + established, "tiktok", "Fitness")

        self.assertEqual(result, "trend report")
        prompt = claude_mock.await_args.kwargs["user_prompt"]
        self.assertIn("hook_velocity", prompt)
        self.assertIn("recent mean", prompt)
        self.assertNotIn("recent-only-marker-abc", prompt)
        self.assertNotIn("established-only-marker-xyz", prompt)


if __name__ == "__main__":
    unittest.main()
