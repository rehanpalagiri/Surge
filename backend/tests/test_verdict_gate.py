"""P3-C: 'Strong craft' must not render above a visibly weak dimension, and the
weakest applicable dimension is surfaced for honest verdict copy."""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from services.gemini import _SCORE_KEYS, _validate_analysis_result


def _result(**overrides):
    base = {k: 7 for k in _SCORE_KEYS}
    base.update(overrides)
    return base


class VerdictGateTest(unittest.TestCase):
    def test_one_sub_five_dimension_blocks_strong_craft(self):
        out = _validate_analysis_result(_result(loop_seamlessness=4))
        self.assertNotEqual(out["verdict"], "Strong craft")
        self.assertEqual(out["verdict"], "Developing craft")
        self.assertEqual(out["weakest_dimension"]["label"], "Ending Strength")
        self.assertEqual(out["weakest_dimension"]["score"], 4.0)

    def test_all_strong_is_strong_craft(self):
        out = _validate_analysis_result(_result())
        self.assertEqual(out["verdict"], "Strong craft")
        self.assertEqual(out["weakest_dimension"]["score"], 7.0)

    def test_five_is_the_boundary_and_still_strong(self):
        # A 5 is "average", not "weak" — it should NOT block Strong craft.
        out = _validate_analysis_result(_result(hook_velocity=8, cut_frequency=8,
                                                text_scannability=8, curiosity_gap=8,
                                                audio_visual_sync=8, loop_seamlessness=5))
        self.assertEqual(out["verdict"], "Strong craft")
        self.assertEqual(out["weakest_dimension"]["score"], 5.0)

    def test_weakest_ignores_not_applicable(self):
        # cut_frequency marked not_applicable (deliberate one-take) must not be the
        # "weakest" — only scored dimensions are eligible.
        r = _result(loop_seamlessness=6)
        r["cut_frequency"] = None
        r["not_applicable"] = {"cut_frequency": "one-take format"}
        out = _validate_analysis_result(r)
        self.assertNotEqual(out["weakest_dimension"]["key"], "cut_frequency")
        self.assertEqual(out["weakest_dimension"]["score"], 6.0)

    def test_missing_or_malformed_emotional_score_is_not_assessed(self):
        for raw_score in (None, "high", True, float("inf")):
            with self.subTest(raw_score=raw_score):
                r = _result()
                r["emotional_analysis"] = {
                    "target_emotions": ["curiosity"],
                    "achieved_score": raw_score,
                }

                emotional = _validate_analysis_result(r)["emotional_analysis"]

                self.assertIsNone(emotional["achieved_score"])
                self.assertFalse(emotional["assessed"])

    def test_genuine_zero_emotional_score_remains_assessed(self):
        r = _result()
        r["emotional_analysis"] = {
            "target_emotions": ["curiosity"],
            "achieved_score": 0,
        }

        emotional = _validate_analysis_result(r)["emotional_analysis"]

        self.assertEqual(emotional["achieved_score"], 0)
        self.assertTrue(emotional["assessed"])


if __name__ == "__main__":
    unittest.main()
