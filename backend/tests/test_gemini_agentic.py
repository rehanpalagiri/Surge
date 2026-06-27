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


if __name__ == "__main__":
    unittest.main()
