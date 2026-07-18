"""Tests for services/seed_statistics.py — the code-first statistics layer that
the "Admin-seed weekly trend synthesis" architecture requires: every number the
narrating LLM later reads must already be computed here, in pure Python, before
any model call happens.

Covers: Pearson r / CI / reportability threshold reuse from tools/craft_correlation,
the deterministic effect-size tier assignment (never left to an LLM), the TikTok
content-driven de-confounding pool vs the Instagram/thin-pool low-confidence
fallback, inter-dimension collinearity flagging, and the recent-vs-established
trend delta with its own sample-size gate.
"""
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from services import seed_statistics as ss


def _seed(rating, dims: dict, *, driver="content", days_old=200):
    """A lightweight stand-in for a SeedVideo row — seed_statistics only reads
    .rating, .gemini_analysis, .posted_at, .created_at."""
    payload = dict(dims)
    payload["performance_driver"] = driver
    return SimpleNamespace(
        rating=rating,
        gemini_analysis=json.dumps(payload),
        posted_at=datetime.now(timezone.utc) - timedelta(days=days_old),
        created_at=datetime.now(timezone.utc) - timedelta(days=days_old),
    )


class DimensionScoresTest(unittest.TestCase):
    def test_parses_only_numeric_dimension_fields(self):
        s = _seed(7, {"hook_velocity": 8, "cut_frequency": "not a number", "junk_field": 1})
        scores = ss._dimension_scores(s)
        self.assertEqual(scores.get("hook_velocity"), 8.0)
        self.assertNotIn("cut_frequency", scores)
        self.assertNotIn("junk_field", scores)

    def test_malformed_json_returns_empty(self):
        s = SimpleNamespace(gemini_analysis="not json", rating=5)
        self.assertEqual(ss._dimension_scores(s), {})

    def test_missing_analysis_returns_empty(self):
        s = SimpleNamespace(gemini_analysis=None, rating=5)
        self.assertEqual(ss._dimension_scores(s), {})


class DeconfoundedPoolTest(unittest.TestCase):
    def test_instagram_always_low_confidence(self):
        seeds = [_seed(7, {"hook_velocity": 7}, driver="unclear") for _ in range(10)]
        pool, reason = ss.select_deconfounded_pool(seeds, "instagram")
        self.assertEqual(len(pool), 10)
        self.assertIsNotNone(reason)
        self.assertIn("Instagram", reason)

    def test_tiktok_pools_to_content_driven_when_enough(self):
        content = [_seed(7, {"hook_velocity": 7}, driver="content") for _ in range(5)]
        distribution = [_seed(3, {"hook_velocity": 3}, driver="distribution") for _ in range(5)]
        pool, reason = ss.select_deconfounded_pool(content + distribution, "tiktok")
        self.assertEqual(len(pool), 5)
        self.assertIsNone(reason)

    def test_tiktok_falls_back_to_full_pool_when_content_driven_is_thin(self):
        content = [_seed(7, {"hook_velocity": 7}, driver="content") for _ in range(2)]  # below MIN_SEEDS
        distribution = [_seed(3, {"hook_velocity": 3}, driver="distribution") for _ in range(5)]
        pool, reason = ss.select_deconfounded_pool(content + distribution, "tiktok")
        self.assertEqual(len(pool), 7)
        self.assertIsNotNone(reason)


class ComputeNicheSeedStatsTest(unittest.TestCase):
    def test_raises_below_min_seeds_floor(self):
        seeds = [_seed(7, {"hook_velocity": 7}) for _ in range(2)]
        with self.assertRaises(ValueError):
            ss.compute_niche_seed_stats(seeds, "tiktok", "Fitness")

    def test_perfect_correlation_is_reported_and_tiered_critical(self):
        # hook_velocity tracks rating exactly (r=+1.0); curiosity_gap is the exact
        # inverse (r=-1.0); cut_frequency is constant (undefined r -> falls to LOW).
        ratings = [9, 8, 7, 6, 5, 4, 3, 2, 9, 3]
        seeds = [
            _seed(r, {"hook_velocity": r, "curiosity_gap": 10 - r, "cut_frequency": 5})
            for r in ratings
        ]
        stats = ss.compute_niche_seed_stats(seeds, "tiktok", "Fitness", min_n=8)
        by_dim = {d["dimension"]: d for d in stats["dimensions"]}

        hv = by_dim["hook_velocity"]
        self.assertAlmostEqual(hv["r"], 1.0, places=3)
        self.assertFalse(hv["insufficient"])
        self.assertEqual(hv["tier"], "CRITICAL")
        self.assertIsNotNone(hv["ci95"])

        cg = by_dim["curiosity_gap"]
        self.assertAlmostEqual(cg["r"], -1.0, places=3)
        self.assertEqual(cg["tier"], "CRITICAL")

        # Constant-valued dimension has no defined correlation and must not be
        # promoted — it's exactly the "no signal, not no effect" case.
        cf = by_dim["cut_frequency"]
        self.assertIsNone(cf["r"])
        self.assertEqual(cf["tier"], "LOW")

        self.assertEqual(stats["n_total"], 10)
        self.assertEqual(stats["n_high"], sum(1 for r in ratings if r >= 6))
        self.assertEqual(stats["n_low"], sum(1 for r in ratings if r <= 4))

    def test_high_low_group_means_reflect_the_split(self):
        seeds = [
            _seed(9, {"hook_velocity": 9}), _seed(8, {"hook_velocity": 8}),
            _seed(7, {"hook_velocity": 7}), _seed(6, {"hook_velocity": 6}),
            _seed(4, {"hook_velocity": 2}), _seed(3, {"hook_velocity": 1}),
            _seed(2, {"hook_velocity": 1}), _seed(1, {"hook_velocity": 0}),
        ]
        stats = ss.compute_niche_seed_stats(seeds, "tiktok", "Fitness", min_n=8)
        hv = next(d for d in stats["dimensions"] if d["dimension"] == "hook_velocity")
        self.assertEqual(hv["n_high"], 4)  # rating >= 6
        self.assertEqual(hv["n_low"], 4)   # rating <= 4
        self.assertGreater(hv["high_mean"], hv["low_mean"])

    def test_dimension_missing_on_most_seeds_is_insufficient(self):
        seeds = [_seed(7, {"hook_velocity": 7}) for _ in range(3)]
        seeds += [_seed(7, {}) for _ in range(7)]  # no dimension scores at all
        stats = ss.compute_niche_seed_stats(seeds, "tiktok", "Fitness", min_n=8)
        hv = next(d for d in stats["dimensions"] if d["dimension"] == "hook_velocity")
        self.assertEqual(hv["n"], 3)
        self.assertTrue(hv["insufficient"])


class TierAssignmentTest(unittest.TestCase):
    def _row(self, dim, r, n=20):
        return {"dimension": dim, "r": r, "insufficient": (r is None or n < 8), "n": n}

    def test_caps_critical_at_two(self):
        rows = [
            self._row("hook_velocity", 0.9),
            self._row("curiosity_gap", 0.8),
            self._row("audio_visual_sync", 0.7),
            self._row("cut_frequency", 0.2),
            self._row("text_scannability", 0.05),
            self._row("loop_seamlessness", 0.15),
        ]
        tiers = ss._assign_tiers(rows)
        critical = [d for d, t in tiers.items() if t == "CRITICAL"]
        self.assertEqual(len(critical), 2)
        self.assertEqual(set(critical), {"hook_velocity", "curiosity_gap"})
        self.assertEqual(tiers["audio_visual_sync"], "HIGH")
        self.assertEqual(tiers["cut_frequency"], "STANDARD")
        self.assertEqual(tiers["text_scannability"], "LOW")
        self.assertEqual(tiers["loop_seamlessness"], "STANDARD")

    def test_does_not_manufacture_a_low_when_every_dimension_is_strong(self):
        # A real result where all six dimensions show a moderate-or-stronger
        # correlation is legitimate — the code must not fake a "weakest link" by
        # downgrading a genuinely CRITICAL/HIGH dimension's tier to misrepresent
        # its measured effect size just to satisfy an "at least one LOW" convention.
        rows = [
            self._row("hook_velocity", 0.9),
            self._row("curiosity_gap", 0.85),
            self._row("audio_visual_sync", 0.7),
            self._row("cut_frequency", 0.6),
            self._row("text_scannability", 0.55),
            self._row("loop_seamlessness", 0.52),
        ]
        tiers = ss._assign_tiers(rows)
        self.assertNotIn("LOW", tiers.values())
        self.assertEqual(set(d for d, t in tiers.items() if t == "CRITICAL"),
                         {"hook_velocity", "curiosity_gap"})
        # Capped out of CRITICAL by the <=2 slot limit, but still HIGH (r >= 0.3) —
        # never demoted to LOW just because the CRITICAL slots were already taken.
        self.assertEqual(tiers["loop_seamlessness"], "HIGH")

    def test_insufficient_or_undefined_r_defaults_low(self):
        rows = [
            self._row("hook_velocity", None, n=20),
            self._row("curiosity_gap", 0.9, n=3),  # strong but below reportable n
        ]
        tiers = ss._assign_tiers(rows)
        self.assertEqual(tiers["hook_velocity"], "LOW")
        self.assertEqual(tiers["curiosity_gap"], "LOW")


class CollinearityTest(unittest.TestCase):
    def test_flags_perfectly_correlated_dimension_pair(self):
        records = []
        for i in range(10):
            dv = {"hook_velocity": float(i), "curiosity_gap": float(i), "cut_frequency": float(10 - i)}
            records.append((SimpleNamespace(rating=i), dv))
        collinearity = ss._collinearity(records, min_n=8)
        flagged_pairs = {(f["a"], f["b"]) for f in collinearity["flagged"]}
        self.assertIn(("hook_velocity", "curiosity_gap"), flagged_pairs)


class ComputeTrendSeedStatsTest(unittest.TestCase):
    def test_raises_below_recent_floor(self):
        seeds = [_seed(7, {"hook_velocity": 7}, days_old=200) for _ in range(5)]  # all established
        with self.assertRaises(ValueError):
            ss.compute_trend_seed_stats(seeds, "tiktok", "Fitness")

    def test_shift_reportable_requires_both_sides_populated(self):
        recent = [_seed(8, {"hook_velocity": 9}, days_old=5) for _ in range(4)]
        established = [_seed(5, {"hook_velocity": 4}, days_old=200) for _ in range(4)]
        stats = ss.compute_trend_seed_stats(recent + established, "tiktok", "Fitness")
        hv = next(d for d in stats["dimensions"] if d["dimension"] == "hook_velocity")
        self.assertTrue(hv["shift_reportable"])
        self.assertGreater(hv["delta"], 0)

    def test_shift_not_reportable_with_no_established_baseline(self):
        recent = [_seed(8, {"hook_velocity": 9}, days_old=5) for _ in range(5)]
        stats = ss.compute_trend_seed_stats(recent, "tiktok", "Fitness")
        hv = next(d for d in stats["dimensions"] if d["dimension"] == "hook_velocity")
        self.assertFalse(hv["shift_reportable"])
        self.assertIsNone(hv["established_mean"])
        self.assertEqual(hv["n_established"], 0)


if __name__ == "__main__":
    unittest.main()
