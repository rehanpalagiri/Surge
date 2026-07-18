"""The Claude scoring pass NEVER fabricates a scorecard.

Because the six scores now live in the Claude pass, a scoring failure cannot degrade
to a guessed scorecard (there are no perception scores to fall back to). Every failure
mode — rate limit / overload / 5xx, refusal, truncation, empty or malformed content, or
a missing API key — must return ``(None, message)`` from ``score_from_perception`` and,
end to end, an error dict from ``analyze_video`` (six zeros + ``error``) so the router
stores ``status="error"``. This mirrors the "error dict → status=error, never a
fabricated report" contract the Gemini path already honors.
"""
import os
import tempfile
import types as _types
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from anthropic import APIConnectionError, APIStatusError, RateLimitError

import services.gemini as gemini
import services.claude_scoring as claude_scoring
from services.claude_scoring import _classify_failure, _shape_scoring, score_from_perception

_PERCEPTION = {
    "rubric_context": {"primary_niche": "NONE", "confidence": "low"},
    "dimension_observations": {"hook_velocity": "a", "cut_frequency": "b", "text_scannability": "c",
                               "curiosity_gap": "d", "audio_visual_sync": "e", "loop_seamlessness": "f"},
    "section_observations": [{"section": "0-2s", "observation": "x"}],
    "emotional_read": {"target_emotions": ["curiosity"], "achieved_score": 6,
                       "what_lands": "x", "what_misses": "y"},
}

_VALID_SCORING = """{
  "dimension_reasoning": {"hook_velocity":"m","cut_frequency":"c","text_scannability":"t",
    "curiosity_gap":"q","audio_visual_sync":"s","loop_seamlessness":"e"},
  "hook_velocity": 7, "cut_frequency": 6, "text_scannability": 5,
  "curiosity_gap": 8, "audio_visual_sync": 6, "loop_seamlessness": 4,
  "not_applicable": {"cut_frequency": "", "text_scannability": ""},
  "strengths": ["s"], "improvements": ["a","b","c"], "analysis_summary": "One. Two. Three.",
  "improvement_plan": [{"area":"Ending Strength","priority":1,"current_score":4,"problem":"p","fix":"f","pattern":"x"}],
  "caption_rewrite": "c", "hook_rewrite": "h",
  "attention_risk_map": [
    {"section":"0-2s","risk":"low","reason":"r","fix":"f"},
    {"section":"2-5s","risk":"medium","reason":"r","fix":"f"},
    {"section":"middle","risk":"medium","reason":"r","fix":"f"},
    {"section":"ending/loop","risk":"high","reason":"r","fix":"f"}],
  "recommended_experiment": {"change":"c","keep_constant":"k","observe":"o"},
  "how_to_amplify": ["a","b"]
}"""


class _ClaudeStub:
    """messages.create raises `exc`, or returns a message with `text`/`stop_reason`."""
    def __init__(self, *, text=None, stop_reason="end_turn", exc=None):
        outer = self
        self.calls = 0
        self.text = text
        self.stop_reason = stop_reason
        self.exc = exc

        class Messages:
            async def create(self, **kwargs):
                outer.calls += 1
                if outer.exc is not None:
                    raise outer.exc
                content = (
                    [_types.SimpleNamespace(type="text", text=outer.text)]
                    if outer.text is not None else []
                )
                return _types.SimpleNamespace(
                    content=content,
                    usage=_types.SimpleNamespace(input_tokens=10, output_tokens=20),
                    model="claude-sonnet-5",
                    stop_reason=outer.stop_reason,
                )

        self.messages = Messages()


# ---- Gemini fake (describe-only perception) for the end-to-end tests ----
_PERCEPTION_JSON = """{
  "rubric_context": {"primary_niche": "NONE", "secondary_niche": "NONE",
    "format": "x", "intent": "y", "confidence": "low", "evidence": []},
  "dimension_observations": {"hook_velocity": "a", "cut_frequency": "b", "text_scannability": "c",
    "curiosity_gap": "d", "audio_visual_sync": "e", "loop_seamlessness": "f"},
  "section_observations": [{"section": "0-2s", "observation": "a"}, {"section": "2-5s", "observation": "b"},
    {"section": "middle", "observation": "c"}, {"section": "ending/loop", "observation": "d"}],
  "emotional_read": {"target_emotions": ["curiosity"], "achieved_score": 6, "what_lands": "x", "what_misses": "y"}
}"""


class _GeminiFile:
    state = _types.SimpleNamespace(name="ACTIVE")
    name = "files/x"
    uri = "https://x/files/x"
    mime_type = "video/mp4"


class _GeminiResp:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = _types.SimpleNamespace(prompt_token_count=1, candidates_token_count=1)


class _GeminiClient:
    def __init__(self):
        outer = self

        class F:
            async def upload(self, file): return _GeminiFile()
            async def get(self, name): return _GeminiFile()
            async def delete(self, name): return None

        class M:
            async def generate_content(self, model, contents, config):
                return _GeminiResp(_PERCEPTION_JSON)

        self.aio = _types.SimpleNamespace(files=F(), models=M())


def _patch_scoring(stub):
    return (
        patch.object(claude_scoring, "client", stub),
        patch.object(claude_scoring, "record_usage_event", new=AsyncMock()),
    )


class ClassifyFailureTest(unittest.TestCase):
    def test_rate_limit_is_transient(self):
        code, msg = _classify_failure(RateLimitError.__new__(RateLimitError))
        self.assertEqual(code, "anthropic_429")
        self.assertIn("capacity", msg.lower())
        self.assertIn("didn't count", msg.lower())

    def test_connection_error_is_transient(self):
        code, msg = _classify_failure(APIConnectionError.__new__(APIConnectionError))
        self.assertIn("capacity", msg.lower())

    def test_5xx_status_is_transient_but_4xx_is_not(self):
        e5 = APIStatusError.__new__(APIStatusError)
        e5.status_code = 503
        code5, msg5 = _classify_failure(e5)
        self.assertEqual(code5, "anthropic_503")
        self.assertIn("capacity", msg5.lower())

        e4 = APIStatusError.__new__(APIStatusError)
        e4.status_code = 400
        code4, msg4 = _classify_failure(e4)
        self.assertEqual(code4, "anthropic_400")
        self.assertNotIn("capacity", msg4.lower())

    def test_unknown_exception_is_non_transient(self):
        code, msg = _classify_failure(RuntimeError("boom"))
        self.assertEqual(code, "RuntimeError")
        self.assertNotIn("capacity", msg.lower())


class ShapeScoringTest(unittest.TestCase):
    def test_drops_dimension_reasoning_and_keeps_scores(self):
        import json
        shaped = _shape_scoring(json.loads(_VALID_SCORING))
        self.assertNotIn("dimension_reasoning", shaped)
        self.assertEqual(shaped["hook_velocity"], 7)
        # not_applicable "" reasons are dropped (dimensions were scored).
        self.assertEqual(shaped["not_applicable"], {})

    def test_null_score_with_reason_becomes_na(self):
        import json
        data = json.loads(_VALID_SCORING)
        data["cut_frequency"] = None
        data["not_applicable"]["cut_frequency"] = "one-take format"
        shaped = _shape_scoring(data)
        self.assertIsNone(shaped["cut_frequency"])
        self.assertEqual(shaped["not_applicable"], {"cut_frequency": "one-take format"})

    def test_null_score_without_reason_is_not_marked_na(self):
        # A guard: a null with a blank reason must NOT be treated as a deliberate
        # format choice — _validate_analysis_result will then reject it.
        import json
        data = json.loads(_VALID_SCORING)
        data["cut_frequency"] = None  # reason stays ""
        shaped = _shape_scoring(data)
        self.assertNotIn("cut_frequency", shaped["not_applicable"])


class ScoreFromPerceptionTest(unittest.IsolatedAsyncioTestCase):
    async def test_happy_path_returns_scores(self):
        stub = _ClaudeStub(text=_VALID_SCORING)
        p1, p2 = _patch_scoring(stub)
        with p1, p2:
            scoring, err = await score_from_perception(_PERCEPTION, "Uncategorized")
        self.assertIsNone(err)
        self.assertEqual(scoring["hook_velocity"], 7)
        self.assertEqual(stub.calls, 1)

    async def test_missing_key_fails_closed_without_calling(self):
        stub = _ClaudeStub(text=_VALID_SCORING)
        p1, p2 = _patch_scoring(stub)
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}), p1, p2:
            scoring, err = await score_from_perception(_PERCEPTION, "Uncategorized")
        self.assertIsNone(scoring)
        self.assertTrue(err)
        self.assertEqual(stub.calls, 0)  # never spent a call

    async def test_exception_returns_failure(self):
        stub = _ClaudeStub(exc=RuntimeError("boom"))
        p1, p2 = _patch_scoring(stub)
        with p1, p2:
            scoring, err = await score_from_perception(_PERCEPTION, "Uncategorized")
        self.assertIsNone(scoring)
        self.assertTrue(err)

    async def test_refusal_returns_failure(self):
        stub = _ClaudeStub(text=_VALID_SCORING, stop_reason="refusal")
        p1, p2 = _patch_scoring(stub)
        with p1, p2:
            scoring, err = await score_from_perception(_PERCEPTION, "Uncategorized")
        self.assertIsNone(scoring)
        self.assertTrue(err)

    async def test_max_tokens_truncation_returns_failure(self):
        stub = _ClaudeStub(text=_VALID_SCORING, stop_reason="max_tokens")
        p1, p2 = _patch_scoring(stub)
        with p1, p2:
            scoring, err = await score_from_perception(_PERCEPTION, "Uncategorized")
        self.assertIsNone(scoring)
        self.assertTrue(err)

    async def test_empty_content_returns_failure(self):
        stub = _ClaudeStub(text=None)  # no text block
        p1, p2 = _patch_scoring(stub)
        with p1, p2:
            scoring, err = await score_from_perception(_PERCEPTION, "Uncategorized")
        self.assertIsNone(scoring)
        self.assertTrue(err)

    async def test_malformed_json_returns_failure(self):
        stub = _ClaudeStub(text="{not valid json")
        p1, p2 = _patch_scoring(stub)
        with p1, p2:
            scoring, err = await score_from_perception(_PERCEPTION, "Uncategorized")
        self.assertIsNone(scoring)
        self.assertTrue(err)


class AnalyzeVideoNeverFabricatesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self._tmp.write(b"\x00\x00\x00\x18ftypmp42")
        self._tmp.close()

    async def asyncTearDown(self):
        os.unlink(self._tmp.name)

    async def _run(self, claude_stub):
        with patch.object(gemini, "client", _GeminiClient()), \
             patch.object(claude_scoring, "client", claude_stub), \
             patch.object(gemini, "record_usage_event", new=AsyncMock()), \
             patch.object(claude_scoring, "record_usage_event", new=AsyncMock()):
            return await gemini.analyze_video(self._tmp.name, niche="Uncategorized")

    async def test_scoring_failure_yields_error_dict_not_scorecard(self):
        result = await self._run(_ClaudeStub(exc=RuntimeError("boom")))
        self.assertTrue(result.get("error"))
        # The six-zero sentinel, never a fabricated scorecard.
        for key in ("hook_velocity", "cut_frequency", "text_scannability",
                    "curiosity_gap", "audio_visual_sync", "loop_seamlessness"):
            self.assertEqual(result[key], 0)
        self.assertEqual(result["verdict"], "Needs revision")

    async def test_refusal_yields_error_dict(self):
        result = await self._run(_ClaudeStub(text=_VALID_SCORING, stop_reason="refusal"))
        self.assertTrue(result.get("error"))

    async def test_happy_path_yields_populated_scorecard(self):
        result = await self._run(_ClaudeStub(text=_VALID_SCORING))
        self.assertNotIn("error", result)
        self.assertEqual(result["hook_velocity"], 7)
        self.assertEqual(result["craft_review_version"], 5)
        # Scores 7,6,5,8,6,4 → 2 strong (<needed 4), 5 workable (>=4) → Developing.
        # Assert the exact verdict so a broken verdict computation can't slip through.
        self.assertEqual(result["verdict"], "Developing craft")


if __name__ == "__main__":
    unittest.main()
