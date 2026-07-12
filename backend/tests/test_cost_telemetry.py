"""P2-C: per-call Gemini cost is derived from measured tokens × list price, and is
NULL only when token counts are unavailable (never a fabricated zero)."""
import os
import unittest
from unittest.mock import patch

from services.telemetry import estimate_gemini_cost_micros, gemini_price_source


class CostTelemetryTest(unittest.TestCase):
    def test_none_tokens_yields_none_cost(self):
        # Honest NULL, not 0, when the provider gave no usage metadata.
        self.assertIsNone(estimate_gemini_cost_micros(None, None))

    def test_cost_from_tokens_matches_list_price(self):
        # 1,000,000 input @ $0.30/M + 200,000 output @ $2.50/M = $0.30 + $0.50 = $0.80
        micros = estimate_gemini_cost_micros(1_000_000, 200_000)
        self.assertEqual(micros, 800_000)  # $0.80 in micro-USD

    def test_partial_tokens_still_costed(self):
        # Only input tokens present → still a real (non-null) cost.
        self.assertEqual(estimate_gemini_cost_micros(1_000_000, None), 300_000)

    def test_env_override_changes_price(self):
        with patch.dict(os.environ, {
            "GEMINI_FLASH_INPUT_PRICE_PER_MTOK": "1.00",
            "GEMINI_FLASH_OUTPUT_PRICE_PER_MTOK": "1.00",
        }):
            self.assertEqual(estimate_gemini_cost_micros(1_000_000, 1_000_000), 2_000_000)
            self.assertEqual(gemini_price_source()["input_usd_per_mtok"], 1.00)

    def test_bad_env_falls_back_to_default(self):
        with patch.dict(os.environ, {"GEMINI_FLASH_INPUT_PRICE_PER_MTOK": "not-a-number"}):
            # Falls back to the $0.30 default rather than crashing.
            self.assertEqual(estimate_gemini_cost_micros(1_000_000, 0), 300_000)


if __name__ == "__main__":
    unittest.main()
