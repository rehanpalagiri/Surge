"""P3-A: a transient Gemini 429 on the perception call self-heals via bounded
backoff instead of dead-ending a first upload; a sustained 429 still propagates
(so the router's 503 + no-credit-charged behavior is unchanged)."""
import os
import tempfile
import types as _types
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")

import services.gemini as gemini
from services.gemini import analyze_video, _GeminiClientError, _GEMINI_MAX_RETRIES

_PERCEPTION = """{
  "rubric_context": {"primary_niche": "NONE", "secondary_niche": "NONE",
    "format": "x", "intent": "y", "confidence": "low", "evidence": []},
  "hook_velocity": 7, "cut_frequency": 6, "text_scannability": 5,
  "curiosity_gap": 8, "audio_visual_sync": 6, "loop_seamlessness": 4,
  "not_applicable": {},
  "section_observations": [
    {"section": "0-2s", "observation": "a"}, {"section": "2-5s", "observation": "b"},
    {"section": "middle", "observation": "c"}, {"section": "ending/loop", "observation": "d"}],
  "emotional_read": {"target_emotions": ["curiosity"], "achieved_score": 6, "what_lands": "x", "what_misses": "y"}
}"""


class _Err429(_GeminiClientError):
    def __init__(self):
        self.code = 429
        self.message = "rate limited"


class _FakeFile:
    state = _types.SimpleNamespace(name="ACTIVE")
    name = "files/x"


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


class _FakeClient:
    def __init__(self, script):
        self.aio = _FakeAio(script)


class GeminiRetryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self._tmp.write(b"\x00\x00\x00\x18ftypmp42")
        self._tmp.close()

    async def asyncTearDown(self):
        os.unlink(self._tmp.name)

    async def test_transient_429_is_retried_then_succeeds(self):
        # perception: 429 then good; reasoning: good.
        client = _FakeClient([_Err429(), _FakeResp(_PERCEPTION), _FakeResp("{}")])
        with patch.object(gemini, "client", client), \
             patch.object(gemini, "record_usage_event", new=AsyncMock()), \
             patch.object(gemini.asyncio, "sleep", new=AsyncMock()) as sleep_mock:
            result = await analyze_video(self._tmp.name, niche="Uncategorized")
        self.assertNotIn("error", result)
        self.assertEqual(result["hook_velocity"], 7)
        self.assertEqual(sleep_mock.await_count, 1)      # one backoff
        self.assertEqual(client.aio.calls, 3)            # 429 + retry + reasoning

    async def test_sustained_429_propagates_after_bounded_retries(self):
        # Every perception attempt 429s → after the cap, the error re-raises so the
        # router returns 503 and rolls back the row (no credit charged).
        client = _FakeClient([_Err429()] * (_GEMINI_MAX_RETRIES + 1))
        with patch.object(gemini, "client", client), \
             patch.object(gemini, "record_usage_event", new=AsyncMock()), \
             patch.object(gemini.asyncio, "sleep", new=AsyncMock()) as sleep_mock:
            with self.assertRaises(_GeminiClientError) as ctx:
                await analyze_video(self._tmp.name, niche="Uncategorized")
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(client.aio.calls, _GEMINI_MAX_RETRIES + 1)
        self.assertEqual(sleep_mock.await_count, _GEMINI_MAX_RETRIES)


if __name__ == "__main__":
    unittest.main()
