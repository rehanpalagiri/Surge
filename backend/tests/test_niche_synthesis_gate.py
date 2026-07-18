"""NICHE_SYNTHESIS_ENABLED stays fenced OFF by default — same shape as
test_grading_unnudged.py's calibration coverage.

Asserts:
  - the flag defaults off;
  - the weekly scheduler entry point no-ops (and never calls Claude) while off;
  - load_niche_synthesis_block returns "" while off even when a NicheInsight row
    already exists, and returns the stored text once the flag is on — proving the
    flag is the only gate;
  - the live grading path (services.gemini.analyze_video) threads the synthesis
    block through to services.claude_scoring.score_from_perception as "" while
    off, and with the stored content once on.

The scoring pass itself (services/claude_scoring.py) is Claude Sonnet 5, not
Gemini — this suite mocks gemini.client for the perception (video) call only and
mocks gemini.score_from_perception directly to capture what analyze_video threads
into it, rather than re-implementing an Anthropic response fake.
"""
import os
import tempfile
import types as _types
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.pop("NICHE_SYNTHESIS_ENABLED", None)  # default OFF for this suite

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import services.gemini as gemini
import services.niche_synthesis as niche_synthesis
from models import Base, NicheInsight
from services.gemini import analyze_video

_PERCEPTION = """{
  "rubric_context": {"primary_niche": "NONE", "secondary_niche": "NONE",
    "format": "x", "intent": "y", "confidence": "low", "evidence": []},
  "hook_velocity": 7, "cut_frequency": 6, "text_scannability": 5,
  "curiosity_gap": 8, "audio_visual_sync": 6, "loop_seamlessness": 4,
  "not_applicable": {},
  "section_observations": [
    {"section": "0-2s", "observation": "a"}, {"section": "2-5s", "observation": "b"},
    {"section": "middle", "observation": "c"}, {"section": "ending/loop", "observation": "d"}],
  "emotional_read": {"target_emotions": ["curiosity"], "achieved_score": 6,
    "what_lands": "x", "what_misses": "y"}
}"""

_SCORING_RESULT = {
    "hook_velocity": 7, "cut_frequency": 6, "text_scannability": 5,
    "curiosity_gap": 8, "audio_visual_sync": 6, "loop_seamlessness": 4,
    "not_applicable": {},
    "strengths": ["x"], "improvements": ["a", "b", "c"],
    "analysis_summary": "s1. s2. s3.", "improvement_plan": [],
    "caption_rewrite": "c", "hook_rewrite": "h",
    "attention_risk_map": [], "recommended_experiment": {},
    "how_to_amplify": ["x", "y"],
}


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
    """Mocks the Gemini perception (video) call only — scoring moved to Claude
    Sonnet 5 (services.claude_scoring), mocked separately at the call site."""

    def __init__(self):
        class F:
            async def upload(self, file):
                return _FakeFile()

            async def get(self, name):
                return _FakeFile()

            async def delete(self, name):
                return None

        class M:
            async def generate_content(self, model, contents, config):
                return _FakeResp(_PERCEPTION)

        self.files = F()
        self.models = M()


class _FakeClient:
    def __init__(self):
        self.aio = _FakeAio()


class NicheSynthesisGateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self._tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self._tmp.write(b"\x00\x00\x00\x18ftypmp42")
        self._tmp.close()

    async def asyncTearDown(self):
        os.unlink(self._tmp.name)
        await self.engine.dispose()

    async def _seed_insight(self, db):
        db.add(NicheInsight(
            platform="tiktok", niche="Fitness",
            insight="UNIQUE-SYNTHESIS-MARKER-98765", seed_count=20,
        ))
        await db.commit()

    def test_flag_defaults_off(self):
        self.assertFalse(niche_synthesis.niche_synthesis_enabled())

    async def test_weekly_run_is_noop_when_disabled(self):
        claude_mock = AsyncMock(side_effect=AssertionError("Claude must not be called"))
        with patch.object(niche_synthesis, "claude_configured", new=lambda: True), \
             patch("services.claude_client.tracked_claude_message", new=claude_mock):
            result = await niche_synthesis.run_weekly_niche_synthesis()
        self.assertEqual(result["status"], "disabled")
        claude_mock.assert_not_awaited()

    async def test_load_block_gated_by_flag(self):
        with patch.object(niche_synthesis, "AsyncSessionLocal", self.sessions):
            async with self.sessions() as db:
                await self._seed_insight(db)

            # Flag OFF (default): nothing injected even though a row exists.
            block = await niche_synthesis.load_niche_synthesis_block("tiktok", "Fitness")
            self.assertEqual(block, "")

            # Flag ON: the same lookup returns the stored text.
            with patch.dict(os.environ, {"NICHE_SYNTHESIS_ENABLED": "1"}):
                block = await niche_synthesis.load_niche_synthesis_block("tiktok", "Fitness")
                self.assertIn("UNIQUE-SYNTHESIS-MARKER-98765", block)

    async def test_grading_stays_blind_by_default(self):
        scoring_mock = AsyncMock(return_value=(_SCORING_RESULT, None))
        with patch.object(niche_synthesis, "AsyncSessionLocal", self.sessions):
            async with self.sessions() as db:
                await self._seed_insight(db)

            fake_client = _FakeClient()
            with patch.object(gemini, "client", fake_client), \
                 patch.object(gemini, "record_usage_event", new=AsyncMock()), \
                 patch.object(gemini, "score_from_perception", new=scoring_mock):
                result = await analyze_video(self._tmp.name, niche="Fitness", niche_raw="Fitness")

        self.assertNotIn("error", result)
        scoring_mock.assert_awaited_once()
        self.assertEqual(scoring_mock.await_args.kwargs["niche_synthesis_block"], "")

    async def test_grading_injects_synthesis_when_enabled(self):
        scoring_mock = AsyncMock(return_value=(_SCORING_RESULT, None))
        with patch.object(niche_synthesis, "AsyncSessionLocal", self.sessions):
            async with self.sessions() as db:
                await self._seed_insight(db)

            fake_client = _FakeClient()
            with patch.object(gemini, "client", fake_client), \
                 patch.object(gemini, "record_usage_event", new=AsyncMock()), \
                 patch.object(gemini, "score_from_perception", new=scoring_mock), \
                 patch.dict(os.environ, {"NICHE_SYNTHESIS_ENABLED": "1"}):
                result = await analyze_video(self._tmp.name, niche="Fitness", niche_raw="Fitness")

        self.assertNotIn("error", result)
        scoring_mock.assert_awaited_once()
        self.assertIn("UNIQUE-SYNTHESIS-MARKER-98765", scoring_mock.await_args.kwargs["niche_synthesis_block"])


if __name__ == "__main__":
    unittest.main()
