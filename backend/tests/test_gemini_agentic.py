"""Unit tests for _merge_passes + _validate_analysis_result under the two-provider
split: the six scores and not_applicable now arrive in the SCORING arg (Claude), while
only the emotional read comes from the perception (Gemini) description. _merge_passes is
never called with an empty scoring dict — a scoring failure returns an error dict
upstream, never a fabricated scorecard — so these tests always pass a real scoring dict.
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from services.gemini import _merge_passes

# Only emotional_read is read from perception by _merge_passes; the rest of the
# description is irrelevant to the merge.
_PERCEPTION = {
    "emotional_read": {
        "target_emotions": ["curiosity"],
        "achieved_score": 6,
        "what_lands": "Clear claim",
        "what_misses": "Weak loop",
    },
}


def _scoring(scores: dict, not_applicable: dict | None = None, **overrides) -> dict:
    """A realistic Claude scoring result: the six scores + a full critique."""
    base = {
        "hook_velocity": 7,
        "cut_frequency": 6,
        "text_scannability": 5,
        "curiosity_gap": 8,
        "audio_visual_sync": 6,
        "loop_seamlessness": 4,
        "strengths": ["Curiosity Gap is a visible strength."],
        "improvements": ["Weak ending", "Static middle", "Dense text"],
        "analysis_summary": "One. Two. Three.",
        "improvement_plan": [
            {"area": "Ending Strength", "priority": 1, "current_score": 4,
             "problem": "trails off", "fix": "add payoff", "pattern": "callback"},
        ],
        "caption_rewrite": "A clearer caption.",
        "hook_rewrite": "Cold open on the proof.",
        "attention_risk_map": [
            {"section": "0-2s", "risk": "low", "reason": "text and motion", "fix": "keep"},
            {"section": "2-5s", "risk": "medium", "reason": "context", "fix": "tighten"},
            {"section": "middle", "risk": "medium", "reason": "explanation", "fix": "cut"},
            {"section": "ending/loop", "risk": "high", "reason": "done", "fix": "payoff"},
        ],
        "recommended_experiment": {"change": "add payoff", "keep_constant": "topic", "observe": "same-age results"},
        "how_to_amplify": ["show payoff sooner", "hold the feeling"],
    }
    base.update(scores)
    if not_applicable is not None:
        base["not_applicable"] = not_applicable
    base.update(overrides)
    return base


class GeminiMergeTest(unittest.TestCase):
    def test_merge_builds_report_from_scoring(self):
        out = _merge_passes(_PERCEPTION, _scoring({}))

        self.assertEqual(out["verdict"], "Developing craft")
        self.assertTrue(out["analysis_summary"])
        self.assertEqual(len(out["improvement_plan"]), 1)
        self.assertEqual(len(out["attention_risk_map"]), 4)
        self.assertTrue(out["recommended_experiment"]["change"])
        # not_applicable absent from the scoring dict → everything scored.
        self.assertEqual(out["not_applicable"], {})
        # Emotional read is carried from the perception description, not the scorer.
        self.assertEqual(out["emotional_analysis"]["achieved_score"], 6)
        self.assertEqual(out["craft_review_version"], 5)


class NotApplicableDimensionsTest(unittest.TestCase):
    def test_one_take_video_gets_na_not_zero(self):
        out = _merge_passes(
            _PERCEPTION,
            _scoring(
                {"cut_frequency": None, "hook_velocity": 8, "loop_seamlessness": 7},
                {"cut_frequency": "one-take format — the continuous shot is the format",
                 "text_scannability": ""},
            ),
        )
        self.assertEqual(list(out["not_applicable"]), ["cut_frequency"])
        self.assertIsNone(out["cut_frequency"])
        # Verdict computed over the 5 applicable dims (needed = ceil(20/6) = 4).
        self.assertIn(out["verdict"], ("Strong craft", "Developing craft"))
        # The scorer never names a not_applicable dimension in the plan, and merge
        # passes the plan through unchanged.
        areas = [item["area"] for item in out["improvement_plan"]]
        self.assertNotIn("Cut Frequency", areas)

    def test_verdict_scales_thresholds_over_applicable_dims(self):
        # 5 applicable dims, 4 strong (>=7), none weak → Strong craft.
        out = _merge_passes(
            _PERCEPTION,
            _scoring(
                {
                    "cut_frequency": None,
                    "hook_velocity": 8,
                    "text_scannability": 7,
                    "curiosity_gap": 8,
                    "audio_visual_sync": 7,
                    "loop_seamlessness": 5,
                },
                {"cut_frequency": "one-take format", "text_scannability": ""},
            ),
        )
        self.assertEqual(out["verdict"], "Strong craft")

    def test_null_on_non_na_allowed_dimension_is_invalid(self):
        # audio_visual_sync can never be n/a; a null there voids the review.
        out = _merge_passes(
            _PERCEPTION,
            _scoring(
                {"cut_frequency": None, "text_scannability": None, "audio_visual_sync": None},
                {"cut_frequency": "one take", "text_scannability": "no text",
                 "audio_visual_sync": "ambient"},
            ),
        )
        self.assertTrue(out.get("error"))

    def test_null_score_without_na_marker_is_invalid(self):
        out = _merge_passes(_PERCEPTION, _scoring({"cut_frequency": None}))
        self.assertTrue(out.get("error"))

    def test_na_marker_with_numeric_score_keeps_the_score(self):
        # If the scorer both scores a dimension and marks it n/a, trust the score.
        out = _merge_passes(
            _PERCEPTION,
            _scoring({"cut_frequency": 6}, {"cut_frequency": "one take", "text_scannability": ""}),
        )
        self.assertEqual(out["not_applicable"], {})
        self.assertEqual(out["cut_frequency"], 6)

    def test_unknown_keys_and_blank_reasons_are_dropped(self):
        out = _merge_passes(
            _PERCEPTION,
            _scoring({}, {"viral_score": "nope", "cut_frequency": "   "}),
        )
        self.assertEqual(out["not_applicable"], {})


if __name__ == "__main__":
    unittest.main()
