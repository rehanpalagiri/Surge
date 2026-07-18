"""P3-A: a transient Gemini 429 on the perception (description) call self-heals via
bounded backoff instead of dead-ending a first upload; a sustained 429 still propagates
(so the router's 503 + no-credit-charged behavior is unchanged). Scoring is a separate
Claude call now, so only ONE Gemini call happens per analysis — the six scores in the
result come from the mocked Claude pass, not from Gemini."""
import os
import tempfile
import types as _types
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import services.gemini as gemini
import services.claude_scoring as claude_scoring
from services.gemini import analyze_video, _GeminiClientError, _GEMINI_MAX_RETRIES

# DESCRIBE-ONLY perception (no scores).
_PERCEPTION = """{
  "rubric_context": {"primary_niche": "NONE", "secondary_niche": "NONE",
    "format": "x", "intent": "y", "confidence": "low", "evidence": []},
  "dimension_observations": {"hook_velocity": "a", "cut_frequency": "b", "text_scannability": "c",
    "curiosity_gap": "d", "audio_visual_sync": "e", "loop_seamlessness": "f"},
  "section_observations": [
    {"section": "0-2s", "observation": "a"}, {"section": "2-5s", "observation": "b"},
    {"section": "middle", "observation": "c"}, {"section": "ending/loop", "observation": "d"}],
  "emotional_read": {"target_emotions": ["curiosity"], "achieved_score": 6, "what_lands": "x", "what_misses": "y"}
}"""

# What the Claude scoring pass returns — the scores land here now.
_SCORING = """{
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


class _Err429(_GeminiClientError):
    def __init__(self):
        self.code = 429
        self.message = "rate limited"


class _FakeFile:
    state = _types.SimpleNamespace(name="ACTIVE")
    name = "files/x"
    uri = "https://generativelanguage.googleapis.com/v1beta/files/x"
    mime_type = "video/mp4"


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = _types.SimpleNamespace(prompt_token_count=1, candidates_token_count=1)


class _FakeAio:
    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

        class F:
            async def upload(self, file):
                return _FakeFile()

            async def get(self, name):
                return _FakeFile()

            async def delete(self, name):
                return None

        class M:
            async def generate_content(m_self, model, contents, config):
                self.calls += 1
                item = self._script.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item

        self.files = F()
        self.models = M()


class _FakeGeminiClient:
    def __init__(self, script):
        self.aio = _FakeAio(script)


class _FakeClaudeMessage:
    def __init__(self, text):
        self.content = [_types.SimpleNamespace(type="text", text=text)]
        self.usage = _types.SimpleNamespace(input_tokens=10, output_tokens=20)
        self.model = "claude-sonnet-5"
        self.stop_reason = "end_turn"


class _FakeClaudeMessages:
    def __init__(self, text):
        self._text = text
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        return _FakeClaudeMessage(self._text)


class _FakeClaudeClient:
    def __init__(self, text=_SCORING):
        self.messages = _FakeClaudeMessages(text)


class GeminiRetryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self._tmp.write(b"\x00\x00\x00\x18ftypmp42")
        self._tmp.close()

    async def asyncTearDown(self):
        os.unlink(self._tmp.name)

    async def test_transient_429_is_retried_then_succeeds(self):
        # perception: 429 then good. Scoring (Claude) is a separate mocked call.
        gclient = _FakeGeminiClient([_Err429(), _FakeResp(_PERCEPTION)])
        cclient = _FakeClaudeClient()
        with patch.object(gemini, "client", gclient), \
             patch.object(claude_scoring, "client", cclient), \
             patch.object(gemini, "record_usage_event", new=AsyncMock()), \
             patch.object(claude_scoring, "record_usage_event", new=AsyncMock()), \
             patch.object(gemini.asyncio, "sleep", new=AsyncMock()) as sleep_mock:
            result = await analyze_video(self._tmp.name, niche="Uncategorized")
        self.assertNotIn("error", result)
        self.assertEqual(result["hook_velocity"], 7)   # from the Claude scoring pass
        self.assertEqual(sleep_mock.await_count, 1)     # one backoff
        self.assertEqual(gclient.aio.calls, 2)          # 429 + retry (no Gemini reasoning)
        self.assertEqual(cclient.messages.calls, 1)     # scored once, after the description

    async def test_sustained_429_propagates_after_bounded_retries(self):
        # Every perception attempt 429s → after the cap, the error re-raises so the
        # router returns 503 and rolls back the row (no credit charged). The Claude
        # scoring pass is never reached.
        gclient = _FakeGeminiClient([_Err429()] * (_GEMINI_MAX_RETRIES + 1))
        cclient = _FakeClaudeClient()
        with patch.object(gemini, "client", gclient), \
             patch.object(claude_scoring, "client", cclient), \
             patch.object(gemini, "record_usage_event", new=AsyncMock()), \
             patch.object(claude_scoring, "record_usage_event", new=AsyncMock()), \
             patch.object(gemini.asyncio, "sleep", new=AsyncMock()) as sleep_mock:
            with self.assertRaises(_GeminiClientError) as ctx:
                await analyze_video(self._tmp.name, niche="Uncategorized")
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(gclient.aio.calls, _GEMINI_MAX_RETRIES + 1)
        self.assertEqual(sleep_mock.await_count, _GEMINI_MAX_RETRIES)
        self.assertEqual(cclient.messages.calls, 0)     # scoring never reached


if __name__ == "__main__":
    unittest.main()
