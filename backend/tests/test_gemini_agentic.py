import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "test-key")

from services.gemini import _merge_passes


class GeminiAgenticMergeTest(unittest.TestCase):
    def test_reasoning_failure_still_returns_usable_report(self):
        perception = {
            "hook_velocity": 7,
            "cut_frequency": 6,
            "text_scannability": 5,
            "curiosity_gap": 8,
            "audio_visual_sync": 6,
            "loop_seamlessness": 4,
            "section_observations": [
                {"section": "0-2s", "observation": "Immediate text and motion."},
                {"section": "2-5s", "observation": "Context continues with dense text."},
                {"section": "middle", "observation": "Static explanation holds."},
                {"section": "ending/loop", "observation": "Ending signals done."},
            ],
            "emotional_read": {
                "target_emotions": ["curiosity"],
                "achieved_score": 6,
                "what_lands": "Clear claim",
                "what_misses": "Weak loop",
            },
        }

        out = _merge_passes(perception, {})

        self.assertEqual(out["verdict"], "Developing craft")
        self.assertTrue(out["analysis_summary"])
        self.assertEqual(len(out["improvement_plan"]), 3)
        self.assertEqual(len(out["attention_risk_map"]), 4)
        self.assertTrue(out["recommended_experiment"]["change"])
        # No applicability info supplied → everything scored, empty map.
        self.assertEqual(out["not_applicable"], {})
        self.assertEqual(out["craft_review_version"], 4)


def _perception(scores: dict, not_applicable: dict | None = None) -> dict:
    base = {
        "hook_velocity": 7,
        "cut_frequency": 6,
        "text_scannability": 5,
        "curiosity_gap": 8,
        "audio_visual_sync": 6,
        "loop_seamlessness": 4,
    }
    base.update(scores)
    if not_applicable is not None:
        base["not_applicable"] = not_applicable
    return base


class NotApplicableDimensionsTest(unittest.TestCase):
    def test_one_take_video_gets_na_not_zero(self):
        out = _merge_passes(
            _perception(
                {"cut_frequency": None, "hook_velocity": 8, "loop_seamlessness": 7},
                {"cut_frequency": "one-take format — the continuous shot is the format"},
            ),
            {},
        )
        self.assertEqual(list(out["not_applicable"]), ["cut_frequency"])
        self.assertIsNone(out["cut_frequency"])
        # Verdict computed over the 5 applicable dims (needed = ceil(20/6) = 4).
        # Scores 8,5,8,6,7 → workable(≥5)=5 ≥ 4 → at least Developing.
        self.assertIn(out["verdict"], ("Strong craft", "Developing craft"))
        # The n/a dimension never appears in the fallback improvement plan.
        areas = [item["area"] for item in out["improvement_plan"]]
        self.assertNotIn("Cut Frequency", areas)

    def test_verdict_scales_thresholds_over_applicable_dims(self):
        # 5 applicable dims, 4 strong (≥7), none weak → Strong craft
        # (old fixed threshold of 4 would also pass; the scaled needed=4).
        out = _merge_passes(
            _perception(
                {
                    "cut_frequency": None,
                    "hook_velocity": 8,
                    "text_scannability": 7,
                    "curiosity_gap": 8,
                    "audio_visual_sync": 7,
                    "loop_seamlessness": 5,
                },
                {"cut_frequency": "one-take format"},
            ),
            {},
        )
        self.assertEqual(out["verdict"], "Strong craft")

    def test_more_than_two_na_is_ignored(self):
        # Overreach guard: 3 n/a markers → field dropped, null scores invalid.
        out = _merge_passes(
            _perception(
                {"cut_frequency": None, "text_scannability": None, "audio_visual_sync": None},
                {
                    "cut_frequency": "one take",
                    "text_scannability": "no text",
                    "audio_visual_sync": "ambient",
                },
            ),
            {},
        )
        self.assertTrue(out.get("error"))

    def test_null_score_without_na_marker_is_invalid(self):
        out = _merge_passes(_perception({"cut_frequency": None}), {})
        self.assertTrue(out.get("error"))

    def test_na_marker_with_numeric_score_keeps_the_score(self):
        # If the model both scores a dimension and marks it n/a, trust the score.
        out = _merge_passes(
            _perception({"cut_frequency": 6}, {"cut_frequency": "one take"}),
            {},
        )
        self.assertEqual(out["not_applicable"], {})
        self.assertEqual(out["cut_frequency"], 6)

    def test_unknown_keys_and_blank_reasons_are_dropped(self):
        out = _merge_passes(
            _perception({}, {"viral_score": "nope", "cut_frequency": "   "}),
            {},
        )
        self.assertEqual(out["not_applicable"], {})


if __name__ == "__main__":
    unittest.main()
