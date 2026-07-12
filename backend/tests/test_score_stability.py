"""P1-B: test-retest reliability of the craft scorer.

An evaluator whose scores drift run-to-run isn't an evaluator. P1-A pins the
perception (scoring) call with temperature=0 + a fixed seed; this test:

  1. asserts that pinning is actually in force on the perception call (a
     regression guard — if determinism is silently dropped, this fails);
  2. proves the scoring PIPELINE is deterministic given a fixed model output
     (replayed fixture scored N times → per-dimension spread 0);
  3. provides a LIVE, opt-in run that scores a real fixture video N times against
     the actual Gemini API and prints the measured max spread — the number to
     cite publicly. It is skipped in CI (no network / no key / no fixture).

Observed max spread (mocked pipeline): 0. Run the live test to record the real
model spread:  RUN_LIVE_SCORE_STABILITY=1 SCORE_FIXTURE=/path/to.mp4 \\
                 python -m unittest tests.test_score_stability
"""
import asyncio
import os
import tempfile
import types as _types
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")

import services.gemini as gemini
from services.gemini import _SCORE_KEYS, _SCORING_SEED, _SCORING_TEMPERATURE, analyze_video

_PERCEPTION_FIXTURE = """{
  "rubric_context": {"primary_niche": "NONE", "secondary_niche": "NONE",
    "format": "tutorial", "intent": "teach", "confidence": "low", "evidence": []},
  "hook_velocity": 7, "cut_frequency": 6, "text_scannability": 5,
  "curiosity_gap": 8, "audio_visual_sync": 6, "loop_seamlessness": 4,
  "not_applicable": {},
  "dimension_evidence": {"hook_velocity": "motion at frame 1", "cut_frequency": "steady cuts",
    "text_scannability": "legible", "curiosity_gap": "open question", "audio_visual_sync": "on beat",
    "loop_seamlessness": "hard cut"},
  "section_observations": [
    {"section": "0-2s", "observation": "text and motion"},
    {"section": "2-5s", "observation": "context"},
    {"section": "middle", "observation": "explanation"},
    {"section": "ending/loop", "observation": "done"}],
  "emotional_read": {"target_emotions": ["curiosity"], "achieved_score": 6,
    "what_lands": "clear claim", "what_misses": "weak loop"}
}"""

_REASONING_FIXTURE = """{
  "strengths": ["Curiosity Gap is a visible strength."],
  "improvements": ["Weak ending", "Static middle", "Dense text"],
  "analysis_summary": "One. Two. Three.",
  "improvement_plan": [
    {"area": "Ending Strength", "priority": 1, "current_score": 4, "problem": "trails off", "fix": "add payoff", "pattern": "callback"},
    {"area": "Text Scannability", "priority": 2, "current_score": 5, "problem": "dense", "fix": "shorten", "pattern": "text-first"},
    {"area": "Cut Frequency", "priority": 3, "current_score": 6, "problem": "static", "fix": "trim holds", "pattern": "jump cut"}],
  "caption_rewrite": "A clearer caption.",
  "hook_rewrite": "Cold open on the proof.",
  "attention_risk_map": [
    {"section": "0-2s", "risk": "low", "reason": "text and motion", "fix": "keep"},
    {"section": "2-5s", "risk": "medium", "reason": "context", "fix": "tighten"},
    {"section": "middle", "risk": "medium", "reason": "explanation", "fix": "cut"},
    {"section": "ending/loop", "risk": "high", "reason": "done", "fix": "payoff"}],
  "recommended_experiment": {"change": "add payoff", "keep_constant": "topic", "observe": "same-age results"},
  "how_to_amplify": ["show payoff sooner", "hold the feeling"]
}"""


class _FakeFile:
    def __init__(self):
        self.state = _types.SimpleNamespace(name="ACTIVE")
        self.name = "files/fixture"


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = _types.SimpleNamespace(
            prompt_token_count=100, candidates_token_count=50)


class _FakeFiles:
    async def upload(self, file):
        return _FakeFile()

    async def get(self, name):
        return _FakeFile()

    async def delete(self, name):
        return None


class _FakeModels:
    """Replays perception/reasoning fixtures in call order and records configs."""
    def __init__(self):
        self.configs = []
        self._i = 0

    async def generate_content(self, model, contents, config):
        self.configs.append(config)
        text = _PERCEPTION_FIXTURE if self._i % 2 == 0 else _REASONING_FIXTURE
        self._i += 1
        return _FakeResp(text)


class _FakeAio:
    def __init__(self):
        self.files = _FakeFiles()
        self.models = _FakeModels()


class _FakeClient:
    def __init__(self):
        self.aio = _FakeAio()


def _spread(runs: list[dict]) -> dict:
    """Per-dimension (max - min) across runs, ignoring not-applicable (None)."""
    out = {}
    for key in _SCORE_KEYS:
        vals = [r[key] for r in runs if isinstance(r.get(key), (int, float))]
        out[key] = (max(vals) - min(vals)) if vals else 0
    return out


async def _score_n_times(video_path: str, n: int) -> list[dict]:
    return [await analyze_video(video_path, niche="Uncategorized") for _ in range(n)]


class ScoreStabilityMockedTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self._tmp.write(b"\x00\x00\x00\x18ftypmp42")
        self._tmp.close()

    async def asyncTearDown(self):
        os.unlink(self._tmp.name)

    async def test_perception_call_is_pinned_deterministic(self):
        fake = _FakeClient()
        with patch.object(gemini, "client", fake), \
             patch.object(gemini, "record_usage_event", new=AsyncMock()):
            await analyze_video(self._tmp.name, niche="Uncategorized")
        # First generate_content call is the perception (scoring) pass.
        perception_cfg = fake.aio.models.configs[0]
        self.assertEqual(perception_cfg.temperature, _SCORING_TEMPERATURE)
        self.assertEqual(perception_cfg.seed, _SCORING_SEED)
        self.assertEqual(perception_cfg.temperature, 0.0)  # not merely "low"

    async def test_repeat_scoring_spread_within_one(self):
        fake = _FakeClient()
        N = 5
        with patch.object(gemini, "client", fake), \
             patch.object(gemini, "record_usage_event", new=AsyncMock()):
            runs = await _score_n_times(self._tmp.name, N)
        spreads = _spread(runs)
        max_spread = max(spreads.values())
        # Deterministic model output → deterministic pipeline → zero drift.
        self.assertLessEqual(max_spread, 1, f"spread too large: {spreads}")
        print(f"\n[P1-B] mocked pipeline max score spread over {N} runs: {max_spread}")

    async def test_spread_helper_catches_real_variance(self):
        # Guard against a vacuous test: the spread computation must actually flag
        # a >1 drift if the model were non-deterministic.
        drifting = [
            {k: 5 for k in _SCORE_KEYS},
            {**{k: 5 for k in _SCORE_KEYS}, "hook_velocity": 8},
        ]
        self.assertGreater(max(_spread(drifting).values()), 1)


@unittest.skipUnless(
    os.getenv("RUN_LIVE_SCORE_STABILITY") == "1" and os.getenv("SCORE_FIXTURE"),
    "live score-stability run is opt-in (set RUN_LIVE_SCORE_STABILITY=1 and SCORE_FIXTURE=/path.mp4)",
)
class ScoreStabilityLiveTest(unittest.IsolatedAsyncioTestCase):
    async def test_live_repeat_scoring_spread_within_one(self):
        video = os.environ["SCORE_FIXTURE"]
        n = int(os.getenv("SCORE_STABILITY_N", "3"))
        runs = await _score_n_times(video, n)
        for r in runs:
            self.assertNotIn("error", r, f"a live scoring failed: {r.get('error')}")
        spreads = _spread(runs)
        max_spread = max(spreads.values())
        print(f"\n[P1-B LIVE] per-dimension spread over {n} runs: {spreads}")
        print(f"[P1-B LIVE] observed max score spread: {max_spread}")
        self.assertLessEqual(max_spread, 1, f"live scores drift > 1: {spreads}")


if __name__ == "__main__":
    unittest.main()
