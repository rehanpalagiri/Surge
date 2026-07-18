"""P1-B: test-retest reliability of the craft scorer under the two-provider split.

Gemini writes the video DESCRIPTION (pinned temperature=0 + fixed seed → the
description reproduces run to run); Claude Sonnet 5 reads that description and produces
the six scores. Sonnet 5 rejects sampling params, so the scoring pass is NOT
temperature-pinnable — score reproducibility is bounded by the provider, not by us.
This suite therefore:

  1. asserts the Gemini description call is still pinned (a regression guard — if
     determinism is silently dropped on the perception call, this fails);
  2. asserts the Claude scoring call sends NO temperature/top_p/top_k (guards against a
     future 400) and uses claude-sonnet-5 + effort="medium" + structured outputs;
  3. proves the scoring PIPELINE is deterministic GIVEN a fixed model output (a fixed
     Gemini description + a fixed Claude scoring, scored N times → per-dimension spread 0);
  4. provides a LIVE, opt-in run that scores a real fixture video N times against the
     real APIs and prints the measured spread — the number to cite publicly. It is
     skipped in CI (no network / no keys / no fixture).

Observed max spread (mocked pipeline): 0. Run the live test to record the real model
spread (now driven by the un-pinnable Claude pass):
  RUN_LIVE_SCORE_STABILITY=1 SCORE_FIXTURE=/path/to.mp4 \\
    python -m unittest tests.test_score_stability
"""
import contextlib
import os
import tempfile
import types as _types
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import services.gemini as gemini
import services.claude_scoring as claude_scoring
from services.gemini import _SCORE_KEYS, _SCORING_SEED, _SCORING_TEMPERATURE, analyze_video

# DESCRIBE-ONLY perception: what Gemini emits now — observations, no scores, no
# dimension_evidence. The scores come from the Claude pass below.
_PERCEPTION_FIXTURE = """{
  "rubric_context": {"primary_niche": "NONE", "secondary_niche": "NONE",
    "format": "tutorial", "intent": "teach", "confidence": "low", "evidence": []},
  "dimension_observations": {
    "hook_velocity": "person already mid-action, text overlay at frame 1",
    "cut_frequency": "steady cuts every 1-2s, no static holds",
    "text_scannability": "large captions, high contrast, above the UI zone",
    "curiosity_gap": "opens on an unresolved question",
    "audio_visual_sync": "cuts land on speech emphasis",
    "loop_seamlessness": "hard cut to black at the end"},
  "section_observations": [
    {"section": "0-2s", "observation": "text and motion"},
    {"section": "2-5s", "observation": "context"},
    {"section": "middle", "observation": "explanation"},
    {"section": "ending/loop", "observation": "done"}],
  "emotional_read": {"target_emotions": ["curiosity"], "achieved_score": 6,
    "what_lands": "clear claim", "what_misses": "weak loop"}
}"""

# What Claude returns — the six scores (matching the structured-output schema) +
# critique. dimension_reasoning is emitted before the scores (evidence-then-score) and
# dropped by _shape_scoring; not_applicable carries "" for scored dimensions.
_SCORING_FIXTURE = """{
  "dimension_reasoning": {"hook_velocity": "motion at frame 1", "cut_frequency": "steady cuts",
    "text_scannability": "legible", "curiosity_gap": "open question", "audio_visual_sync": "on beat",
    "loop_seamlessness": "hard cut"},
  "hook_velocity": 7, "cut_frequency": 6, "text_scannability": 5,
  "curiosity_gap": 8, "audio_visual_sync": 6, "loop_seamlessness": 4,
  "not_applicable": {"cut_frequency": "", "text_scannability": ""},
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


# ---- Gemini fakes (video description pass) ----
class _FakeFile:
    def __init__(self):
        self.state = _types.SimpleNamespace(name="ACTIVE")
        self.name = "files/fixture"
        self.uri = "https://generativelanguage.googleapis.com/v1beta/files/fixture"
        self.mime_type = "video/mp4"


class _FakeGeminiResp:
    def __init__(self, text, model_version=None):
        self.text = text
        self.model_version = model_version
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
    """Records the perception config so the pinning assertion can inspect it."""
    def __init__(self):
        self.configs = []

    async def generate_content(self, model, contents, config):
        self.configs.append(config)
        return _FakeGeminiResp(_PERCEPTION_FIXTURE, model_version="served-perception-version")


class _FakeAio:
    def __init__(self):
        self.files = _FakeFiles()
        self.models = _FakeModels()


class _FakeGeminiClient:
    def __init__(self):
        self.aio = _FakeAio()


# ---- Claude fakes (scoring pass) ----
class _FakeClaudeMessage:
    def __init__(self, text, model="claude-sonnet-5", stop_reason="end_turn"):
        self.content = [_types.SimpleNamespace(type="text", text=text)]
        self.usage = _types.SimpleNamespace(input_tokens=120, output_tokens=240)
        self.model = model
        self.stop_reason = stop_reason


class _FakeClaudeMessages:
    def __init__(self, text):
        self._text = text
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeClaudeMessage(self._text)


class _FakeClaudeClient:
    def __init__(self, text=_SCORING_FIXTURE):
        self.messages = _FakeClaudeMessages(text)


@contextlib.contextmanager
def _patched(gemini_client, claude_client, usage_mock=None):
    """Patch both provider clients + swallow telemetry in both provider modules
    (each imported record_usage_event into its own namespace)."""
    um = usage_mock or AsyncMock()
    with patch.object(gemini, "client", gemini_client), \
         patch.object(claude_scoring, "client", claude_client), \
         patch.object(gemini, "record_usage_event", new=um), \
         patch.object(claude_scoring, "record_usage_event", new=um):
        yield um


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
        gc = _FakeGeminiClient()
        with _patched(gc, _FakeClaudeClient()):
            await analyze_video(self._tmp.name, niche="Uncategorized")
        # First (and only) Gemini call is the perception/description pass.
        perception_cfg = gc.aio.models.configs[0]
        self.assertEqual(perception_cfg.temperature, _SCORING_TEMPERATURE)
        self.assertEqual(perception_cfg.seed, _SCORING_SEED)
        self.assertEqual(perception_cfg.temperature, 0.0)  # not merely "low"

    async def test_scoring_call_uses_sonnet_medium_without_sampling(self):
        gc, cc = _FakeGeminiClient(), _FakeClaudeClient()
        with _patched(gc, cc):
            await analyze_video(self._tmp.name, niche="Uncategorized")
        self.assertEqual(len(cc.messages.calls), 1)
        kwargs = cc.messages.calls[0]
        self.assertEqual(kwargs["model"], "claude-sonnet-5")
        self.assertEqual(kwargs["output_config"]["effort"], "medium")
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(kwargs["thinking"], {"type": "adaptive"})
        # Sonnet 5 rejects sampling params with a 400 — the scoring call must send none.
        for banned in ("temperature", "top_p", "top_k"):
            self.assertNotIn(banned, kwargs, f"scoring call must not send {banned}")

    async def test_repeat_scoring_spread_within_one(self):
        N = 5
        with _patched(_FakeGeminiClient(), _FakeClaudeClient()):
            runs = [await analyze_video(self._tmp.name, niche="Uncategorized") for _ in range(N)]
        spreads = _spread(runs)
        max_spread = max(spreads.values())
        # Deterministic model outputs → deterministic pipeline → zero drift. (The real
        # Claude pass is un-pinnable; the live test measures its spread.)
        self.assertLessEqual(max_spread, 1, f"spread too large: {spreads}")
        print(f"\n[P1-B] mocked pipeline max score spread over {N} runs: {max_spread}")

    async def test_served_model_versions_are_recorded_for_both_passes(self):
        usage_mock = AsyncMock()
        with _patched(_FakeGeminiClient(), _FakeClaudeClient(), usage_mock=usage_mock):
            await analyze_video(self._tmp.name, niche="Uncategorized")

        events = {
            call.kwargs["operation"]: call.kwargs
            for call in usage_mock.await_args_list
        }
        perception = events["video_craft_perception"]
        self.assertEqual(perception["provider"], "google_gemini")
        self.assertEqual(perception["model_version"], "served-perception-version")
        scoring = events["video_craft_scoring"]
        self.assertEqual(scoring["provider"], "anthropic")
        self.assertEqual(scoring["model"], "claude-sonnet-5")
        self.assertEqual(scoring["model_version"], "claude-sonnet-5")  # resp.model
        self.assertTrue(scoring["success"])

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
    async def test_live_repeat_scoring_spread(self):
        video = os.environ["SCORE_FIXTURE"]
        n = int(os.getenv("SCORE_STABILITY_N", "3"))
        runs = await _score_n_times(video, n)
        for r in runs:
            self.assertNotIn("error", r, f"a live scoring failed: {r.get('error')}")
        spreads = _spread(runs)
        max_spread = max(spreads.values())
        # Gemini's description is pinned; the Claude scoring pass is not. This prints
        # the real per-dimension spread — the number to cite. Not asserted tightly,
        # since the un-pinnable pass may legitimately move a point or two.
        print(f"\n[P1-B LIVE] per-dimension spread over {n} runs: {spreads}")
        print(f"[P1-B LIVE] observed max score spread: {max_spread}")


if __name__ == "__main__":
    unittest.main()
