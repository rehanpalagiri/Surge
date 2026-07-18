"""Tests for services/claude_client.py — the Claude Opus 4.8 wrapper used by the
weekly niche/trend synthesis. Covers the "not configured" fail-closed path, the
truncated-response guard (a partial narration must never be silently stored), and
the NULL-safe cost estimator (never fabricate a cost from an absent token count).
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import services.claude_client as claude_client


def _resp(text, *, stop_reason="end_turn", input_tokens=100, output_tokens=50):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)] if text else [],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason=stop_reason,
    )


class ClaudeClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_raises_when_not_configured(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch.object(claude_client, "_client", None):
                with self.assertRaises(RuntimeError):
                    await claude_client.tracked_claude_message(
                        operation="test", system="s", user_prompt="p"
                    )

    async def test_truncated_response_raises_instead_of_returning_partial_text(self):
        fake_client = SimpleNamespace(
            messages=SimpleNamespace(
                create=AsyncMock(return_value=_resp("partial narration...", stop_reason="max_tokens"))
            )
        )
        with patch.object(claude_client, "_get_client", return_value=fake_client), \
             patch.object(claude_client, "record_usage_event", new=AsyncMock()) as record_mock:
            with self.assertRaises(ValueError) as ctx:
                await claude_client.tracked_claude_message(operation="test", system="s", user_prompt="p")
        self.assertIn("truncated", str(ctx.exception).lower())
        record_mock.assert_awaited_once()
        self.assertFalse(record_mock.await_args.kwargs["success"])
        self.assertEqual(record_mock.await_args.kwargs["error_code"], "truncated_max_tokens")

    async def test_successful_response_returns_text_and_records_usage(self):
        fake_client = SimpleNamespace(
            messages=SimpleNamespace(create=AsyncMock(return_value=_resp("the narrated report")))
        )
        with patch.object(claude_client, "_get_client", return_value=fake_client), \
             patch.object(claude_client, "record_usage_event", new=AsyncMock()) as record_mock:
            result = await claude_client.tracked_claude_message(operation="test", system="s", user_prompt="p")
        self.assertEqual(result, "the narrated report")
        record_mock.assert_awaited_once()
        self.assertTrue(record_mock.await_args.kwargs["success"])

    async def test_empty_response_raises(self):
        fake_client = SimpleNamespace(
            messages=SimpleNamespace(create=AsyncMock(return_value=_resp("")))
        )
        with patch.object(claude_client, "_get_client", return_value=fake_client), \
             patch.object(claude_client, "record_usage_event", new=AsyncMock()):
            with self.assertRaises(ValueError):
                await claude_client.tracked_claude_message(operation="test", system="s", user_prompt="p")


class CostEstimateTest(unittest.TestCase):
    def test_none_when_both_token_counts_missing(self):
        self.assertIsNone(claude_client.estimate_claude_cost_micros(None, None))

    def test_computes_cost_from_partial_token_counts(self):
        # Missing side treated as 0, never fabricated — mirrors
        # services.telemetry.estimate_gemini_cost_micros's NULL-handling contract.
        cost = claude_client.estimate_claude_cost_micros(1_000_000, None)
        self.assertIsNotNone(cost)
        self.assertGreater(cost, 0)


if __name__ == "__main__":
    unittest.main()
