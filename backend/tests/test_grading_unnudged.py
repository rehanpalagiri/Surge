"""P2-B: the AI-audits-AI calibration path stays fenced OFF by default.

Asserts that with SURGE_CALIBRATION_ENABLED unset (the default):
  - the live grading path applies NO calibration nudge (calibration_version 0,
    scores equal the raw perception scores);
  - the grade-time note read (load_calibration_note) returns None even when a note
    exists in the table — and returns it once the flag is on, proving the flag is
    the gate;
  - the note generator and the correction audit refuse to produce AI opinion;
  - grading has no import wire to the calibration path at all (the "grep" check).
"""
import os
import tempfile
import types as _types
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.pop("SURGE_CALIBRATION_ENABLED", None)  # default OFF for this suite

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import services.gemini as gemini
import services.seed_correction as seed_correction
from models import Base, CalibrationNote, UserAnalysis
from services.calibration import (
    calibration_enabled,
    generate_calibration_note,
    load_calibration_note,
)
from services.gemini import _SCORE_KEYS, analyze_video

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
_EXPECTED_SCORES = {"hook_velocity": 7, "cut_frequency": 6, "text_scannability": 5,
                    "curiosity_gap": 8, "audio_visual_sync": 6, "loop_seamlessness": 4}


class _FakeFile:
    state = _types.SimpleNamespace(name="ACTIVE")
    name = "files/x"


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = _types.SimpleNamespace(prompt_token_count=1, candidates_token_count=1)


class _FakeAio:
    def __init__(self):
        outer = self

        class F:
            async def upload(self, file):
                return _FakeFile()

            async def get(self, name):
                return _FakeFile()

            async def delete(self, name):
                return None

        class M:
            async def generate_content(self, model, contents, config):
                # Perception first, then a reasoning failure (empty) → validator fills
                # defaults from the perception scores. Scores must survive untouched.
                outer._n += 1
                if outer._n == 1:
                    return _FakeResp(_PERCEPTION)
                raise RuntimeError("reasoning intentionally skipped for this test")

        self._n = 0
        self.files = F()
        self.models = M()


class _FakeClient:
    def __init__(self):
        self.aio = _FakeAio()


class GradingUnnudgedTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_flag_defaults_off(self):
        self.assertFalse(calibration_enabled())

    async def test_grading_applies_no_calibration_nudge(self):
        with patch.object(gemini, "client", _FakeClient()), \
             patch.object(gemini, "record_usage_event", new=AsyncMock()):
            result = await analyze_video(self._tmp.name, niche="Uncategorized")
        self.assertNotIn("error", result)
        self.assertEqual(result["calibration_version"], 0)
        for key in _SCORE_KEYS:
            self.assertEqual(result[key], _EXPECTED_SCORES[key],
                             f"{key} was nudged away from the raw perception score")

    async def _seed_note(self, db):
        db.add(CalibrationNote(
            platform="tiktok", niche="Fitness",
            note_json='{"overall_tendency": "over_rate", "dimension_adjustments": {"hook_velocity": -1.0}, "directive": "lower hooks"}',
            sample_count=20,
        ))
        await db.commit()

    async def test_note_read_gated_by_flag(self):
        async with self.sessions() as db:
            await self._seed_note(db)
            # Flag OFF (default): grader gets nothing, even though a note exists.
            self.assertIsNone(await load_calibration_note(db, "tiktok", "Fitness"))
            # Flag ON: the same call returns the note → the flag is the only gate.
            with patch.dict(os.environ, {"SURGE_CALIBRATION_ENABLED": "1"}):
                note = await load_calibration_note(db, "tiktok", "Fitness")
                self.assertIsInstance(note, dict)
                self.assertEqual(note["overall_tendency"], "over_rate")

    async def test_generate_note_refuses_when_disabled(self):
        with self.assertRaises(ValueError) as ctx:
            await generate_calibration_note("tiktok", "Fitness")
        self.assertIn("disabled", str(ctx.exception).lower())

    async def test_audit_prediction_is_noop_when_disabled(self):
        # A row that WOULD be audited if the path were live (mature views, likes,
        # scores with the legacy overall_score, thinking mode).
        async with self.sessions() as db:
            a = UserAnalysis(
                filename="v.mp4", niche="Fitness", platform="tiktok",
                scores_json='{"overall_score": 7, "hook_velocity": 8}',
                verdict="Strong craft", actual_views=50_000, actual_likes=5_000,
                mode="thinking",
            )
            db.add(a)
            await db.commit()
            await db.refresh(a)
            aid = a.id

        gemini_mock = AsyncMock(side_effect=AssertionError("Gemini must not be called"))
        with patch.object(seed_correction, "AsyncSessionLocal", self.sessions), \
             patch.object(seed_correction, "tracked_generate_content", new=gemini_mock):
            await seed_correction.audit_prediction(aid)

        gemini_mock.assert_not_awaited()
        async with self.sessions() as db:
            a = await db.get(UserAnalysis, aid)
            self.assertIsNone(a.correction_json)

    def test_grading_has_no_calibration_import_wire(self):
        # Operationalizes "grep confirms no live import path enables it": the grading
        # module must not import or call into the calibration path.
        with open(gemini.__file__) as fh:
            src = fh.read()
        self.assertNotIn("from services.calibration", src)
        self.assertNotIn("import calibration", src)
        self.assertNotIn("load_calibration_note", src)


if __name__ == "__main__":
    unittest.main()
