"""Seed-analysis pipeline.

When a seed video is added (admin, harvest, or auto-promoted user video) we send it
to Gemini ONCE to score the video's CRAFT — the 6 dimensions — *blind to the view/like
counts*. The outcome label (`seed_quality` + `performance_driver` + `driver_confidence`)
is then computed in CODE from the real counts via `score_outcome()`, NOT by the model.

Why the split: asking one LLM call to both judge craft AND derive a rating from the counts
let the counts leak into the craft scores (anchoring), and made the rating a noisy LLM guess
that only *hoped* to obey the de-confound / thin-sample / linkage rules. Separating them means:
  - craft scores can't anchor — the model never sees the counts;
  - the rating is 100% deterministic and consistent (same counts → same rating);
  - the de-confound, thin-sample cap, and driver↔rating linkage are ENFORCED in code.

The full JSON (craft fields + the code-computed outcome fields) is stored on the seed row
(`gemini_analysis`); `seed_quality` becomes the seed's `rating`. The video file is deleted
after analysis — the JSON is the durable artifact, read back into niche synthesis + live scoring.

This module reuses the Gemini client, `_PLATFORM_CONTEXT`, and the upload→poll-ACTIVE→
generate→delete pattern from `services.gemini` so there is one source of truth for Gemini I/O.
"""

import json
import asyncio
import os
import time
from typing import Optional

from google.genai import types

from services.gemini import client, _PLATFORM_CONTEXT, _GRADING_SYSTEM_INSTRUCTION
from services.telemetry import record_usage_event, response_token_usage

# Below this view count, like-rate is statistical noise (a 40-view / 9-like video is
# a 22% like-rate but proves nothing). Such seeds get the dormant band (5) — which
# select_seed_examples() injects into NEITHER bucket, so they teach nothing.
LIKE_RATE_MIN_VIEWS = 10_000

# A sub-2% like-rate is only a DISTRIBUTION win (reach carried weak content) when reach
# was genuinely large. Below this, low engagement reflects weak CONTENT, not reach — so the
# seed stays a LOW-performer teaching example instead of being discarded as "distribution".
DISTRIBUTION_MIN_VIEWS = 100_000


def score_outcome(view_count: Optional[int], like_count: int) -> tuple[int, str, str]:
    """Deterministically derive (seed_quality, performance_driver, driver_confidence)
    from the REAL counts — pure arithmetic, never the LLM. This is what makes the rating
    consistent and the de-confound / thin-sample / linkage rules enforceable in code.

    TikTok (views present, >= LIKE_RATE_MIN_VIEWS): rating tracks like-rate (likes/views),
    a reach-normalized content signal. High views + weak like-rate = "distribution" (reach
    won, not content) and is capped low. Thin samples get the dormant band 5 (too few views
    for like-rate to mean anything). Instagram (views hidden): falls back to absolute like
    bands with driver="unclear", because content and reach cannot be separated without views.

    NOTE for niche synthesis (#2): "unclear" covers Instagram seeds (the only signal they
    have) and thin samples — its filter should discard only "distribution", keeping
    content/mixed/unclear, so Instagram still feeds its rubric.
    """
    # Instagram / no usable view count — like-rate uncomputable, reach can't be factored out.
    if view_count is None or view_count <= 0:
        if like_count >= 100_000:
            return 8, "unclear", "low"
        if like_count >= 20_000:
            return 6, "unclear", "low"
        if like_count >= 2_000:
            return 4, "unclear", "low"
        return 2, "unclear", "low"

    # Thin sample — like-rate on a tiny view count is noise. Dormant band; teaches nothing.
    if view_count < LIKE_RATE_MIN_VIEWS:
        return 5, "unclear", "low"

    like_rate = like_count / view_count
    if like_rate >= 0.10:
        return 9, "content", "high"          # exceptional engagement → content earned it
    if like_rate >= 0.05:
        return 7, "content", "high"          # strong
    if like_rate >= 0.02:
        return 5, "mixed", "medium"          # average — dormant, ambiguous driver
    # Weak engagement (<2%). Only a "distribution" win when reach was genuinely large —
    # otherwise it is just weak CONTENT and must stay a LOW-performer example, not be
    # discarded by #2's filter.
    if view_count >= DISTRIBUTION_MIN_VIEWS:
        return 3, "distribution", "high"     # large reach + <2% likes → reach carried it
    return 3, "content", "high"              # modest reach + <2% likes → genuinely weak content


# The six craft dimensions the niche synthesis reads back (services.craft_insights.DIMENSIONS).
_CRAFT_DIMS = (
    "hook_velocity", "cut_frequency", "text_scannability",
    "curiosity_gap", "audio_visual_sync", "loop_seamlessness",
)


def build_user_seed_analysis(review: dict, driver: str, driver_confidence: str) -> dict:
    """Build a seed-schema ``gemini_analysis`` blob from a user's craft review, so a
    user upload can enter the seed pool WITHOUT a second (paid) Gemini call.

    The live craft review (``services.gemini.analyze_video``) is itself blind to the
    view/like counts, so its six dimension scores are already a valid counts-blind
    craft record — the exact guarantee the admin/harvest seed-analysis pass provides.
    ``performance_driver`` / ``driver_confidence`` are the CODE-derived outcome labels
    from ``score_outcome()`` (never the model's guess), matching the seed pipeline's
    craft-blind / code-rated split. Shape is what ``seed_statistics._dimension_scores``
    and ``score_outcome``-derived ``rating`` on the stored ``SeedVideo`` row read.
    """
    blob: dict = {d: review[d] for d in _CRAFT_DIMS if isinstance(review.get(d), (int, float))}
    blob["performance_driver"] = driver
    blob["driver_confidence"] = driver_confidence
    # Provenance marker so a future reader can tell a user-upload seed (craft copied
    # from the live review) from a hand-analyzed admin/harvest seed.
    blob["source"] = "user_upload"
    return blob


def _build_seed_prompt(platform: str, niche: str) -> str:
    """Craft-only prompt. The model sees ONLY the video — never the counts — so its
    dimension scores cannot anchor to a rating. The outcome fields are added afterward
    by score_outcome()."""
    ctx = _PLATFORM_CONTEXT.get(platform, _PLATFORM_CONTEXT["tiktok"])
    pname = ctx["name"]

    return f"""ROLE: You are writing a machine-readable CRAFT record for a video scoring AI.
Your reader is another AI. Optimize for information density — every token must carry signal.
No prose filler. No hedging. State mechanisms directly.

SUBJECT: {pname} video | Niche: {niche}

CRITICAL: You are shown ONLY the video. You have NO view counts, like counts, watch-time, or any
performance data — and you must NOT guess or reference them. Score the CRAFT of what you observe on
screen. Do not speculate about how many views or likes this got, or whether it "went viral".

--- DIMENSION SCORING (0-10) ---
Use these exact shorthand codes. Judge only what is OBSERVABLE on screen. You may describe craft and
INFER likely effect (marked as inference) — but never assert measured retention/watch-time/completion.

HV (hook_velocity): How fast is the viewer's scroll-reason eliminated?
  10 = premise + open question within 2s, zero warm-up | 7 = clear value by s3-4 | 4 = premise clear but no urgency | 0 = creator intro / logo / "hey guys"

CF (cut_frequency): Does edit pacing sustain attention without losing clarity?
  10 = every cut earns its place, rhythm matches energy | 7 = active with minor dead holds | 4 = irregular, energy-less | 0 = single static shot, >10s holds

TS (text_scannability): Does on-screen text deliver value with sound muted?
  10 = muted viewer loses nothing | 7 = helpful overlays on key moments | 4 = captions audio only | 0 = none, or clutter

CG (curiosity_gap): Does the opening force a specific unresolved question?
  10 = named question by s5 unanswerable without watching | 7 = clear interest hook | 4 = mild interest, easy to scroll | 0 = no tension / resolved statement

AVS (audio_visual_sync): Does audio amplify and sync with the visuals?
  10 = beats land on cuts, emphasis aligns | 7 = good choice, roughly synced | 4 = generic, ignores rhythm | 0 = audio fights content

LS (loop_seamlessness / ending strength): Does the ending earn the finish — rewatch/share impulse?
  10 = loops to start OR converting CTA | 7 = satisfying close, weak loop | 4 = clean end, no pull | 0 = hard cut / fade signalling "done"

--- OUTPUT FIELD RULES ---

what_happens: Pure timestamped description, zero evaluation. 2 sentences max.
  Format: "s0: [what viewer sees/hears]. s[N]-[M]: [events]. Ends: [final frame/action]."

performance_reason: 3 sentences naming the 2 STRONGEST and the single WEAKEST dimension, each tied to a
  specific on-screen moment. Use HV/CF/TS/CG/AVS/LS codes. Pure CRAFT — no performance/outcome claims,
  no watch-time claims. Format each sentence: [code] [element at sN] → [why it helps/hurts craft].

patterns — 6 items each, one per dimension in order [HV, CF, TS, CG, AVS, LS], under 15 words.
  replicate: "HV: [specific replicable structure]"
  avoid:     "HV: [specific failure pattern]"

seed_summary: Dense shorthand, no prose. One line per code:
  HV:[score] [opening format at s0-s2, does it eliminate scroll-reason]
  CF:[score] [edit pattern, energy match]
  TS:[score] [text strategy, muted-watchable yes/no]
  CG:[score] [open-loop type]
  AVS:[score] [audio type + sync quality]
  LS:[score] [ending type + rewatch signal]
  DRIVER: [single STRONGEST craft element — one causal sentence about craft]
  WEAK: [single biggest craft drag — what a future creator must fix]

--- JSON SCHEMA ---
Return ONLY valid JSON. No markdown. No text outside the JSON. Score the 6 craft dimensions from what
you SEE — you have no counts to anchor to.
{{
  "hook_velocity": <0-10>,
  "cut_frequency": <0-10>,
  "text_scannability": <0-10>,
  "curiosity_gap": <0-10>,
  "audio_visual_sync": <0-10>,
  "loop_seamlessness": <0-10>,
  "what_happens": "<2 timestamped sentences, pure description>",
  "performance_reason": "<3 sentences, craft only, dimension codes, no outcome/watch-time claims>",
  "patterns": {{
    "replicate": ["HV: <15 words>", "CF: <15 words>", "TS: <15 words>", "CG: <15 words>", "AVS: <15 words>", "LS: <15 words>"],
    "avoid":     ["HV: <15 words>", "CF: <15 words>", "TS: <15 words>", "CG: <15 words>", "AVS: <15 words>", "LS: <15 words>"]
  }},
  "seed_summary": "<HV/CF/TS/CG/AVS/LS lines + DRIVER + WEAK — structured shorthand, no prose>"
}}"""


async def analyze_seed_video(
    video_path: str,
    platform: str,
    niche: str,
    view_count: Optional[int],
    like_count: int,
) -> dict:
    """Score a seed video's craft (Gemini, blind to counts), then attach the code-computed
    outcome (rating/driver/confidence). Returns the parsed dict on success, or a dict with an
    "error" key on any failure. The caller MUST treat a missing/invalid "seed_quality" as a
    failure and not persist the seed.
    """
    started = time.perf_counter()
    input_bytes = os.path.getsize(video_path) if os.path.exists(video_path) else None
    try:
        prompt = _build_seed_prompt(platform, niche)

        uploaded = await client.aio.files.upload(file=video_path)

        # Poll until ACTIVE (same pattern as user-video analysis).
        max_wait = 120
        waited = 0
        while uploaded.state.name != "ACTIVE":
            if uploaded.state.name == "FAILED":
                return {"error": "Gemini failed to process the seed video file."}
            if waited >= max_wait:
                return {"error": "Seed video processing timed out."}
            await asyncio.sleep(5)
            waited += 5
            uploaded = await client.aio.files.get(name=uploaded.name)

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[uploaded, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,  # craft scores stay stable run-to-run
                system_instruction=_GRADING_SYSTEM_INSTRUCTION,
            ),
        )

        # Delete the Gemini-side file early (Gemini auto-expires after 48h anyway).
        try:
            await client.aio.files.delete(name=uploaded.name)
        except Exception:
            pass  # Non-fatal

        data = json.loads(response.text)
        if not isinstance(data, dict) or "hook_velocity" not in data:
            return {"error": "Seed analysis response missing craft dimensions."}

        # Outcome is computed in CODE from the real counts — deterministic, de-confounded,
        # rules (thin-sample cap, distribution↔rating linkage) enforced rather than requested.
        rating, driver, confidence = score_outcome(view_count, like_count)
        data["seed_quality"] = rating
        data["performance_driver"] = driver
        data["driver_confidence"] = confidence
        input_tokens, output_tokens = response_token_usage(response)
        await record_usage_event(
            operation="seed_craft_analysis",
            provider="google_gemini",
            model="gemini-2.5-flash",
            success=True,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_bytes=input_bytes,
            output_bytes=len((response.text or "").encode("utf-8")),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return data

    except json.JSONDecodeError as e:
        await record_usage_event(
            operation="seed_craft_analysis", provider="google_gemini",
            model="gemini-2.5-flash", success=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_bytes=input_bytes, error_code="invalid_json",
        )
        return {"error": f"Failed to parse seed analysis as JSON: {e}"}
    except Exception as e:  # noqa: BLE001
        await record_usage_event(
            operation="seed_craft_analysis", provider="google_gemini",
            model="gemini-2.5-flash", success=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_bytes=input_bytes, error_code=type(e).__name__,
        )
        return {"error": str(e)}
