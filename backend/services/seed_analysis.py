"""Seed-analysis pipeline.

When an admin uploads a reference ("seed") video, we send it to Gemini ONCE to
produce a causal, AI-consumption-only performance writeup. That JSON is stored on
the seed row (`gemini_analysis`) and the extracted `virality_rating` becomes the
seed's `rating`. The video file itself is deleted afterwards — the JSON is the
durable artifact, read back into the niche intelligence synthesis and live scoring
prompt for Thinking/Deep modes.

This module deliberately reuses the Gemini client, `_PLATFORM_CONTEXT`, and the
upload→poll-ACTIVE→generate→delete pattern from `services.gemini` so there is one
source of truth for how we talk to Gemini.
"""

import json
import asyncio
from typing import Optional

from google.genai import types

from services.gemini import client, _PLATFORM_CONTEXT


def _build_seed_prompt(
    platform: str, niche: str, view_count: Optional[int], like_count: int
) -> str:
    ctx = _PLATFORM_CONTEXT.get(platform, _PLATFORM_CONTEXT["tiktok"])
    pname = ctx["name"]

    if view_count is not None:
        perf_line = f"Performance: {view_count:,} views · {like_count:,} likes"
        rating_anchor = (
            "2M+ views=8-9 | 800K-2M=6-7 | 100K-800K=4-5 | <100K=2-3 | <10K=0-1. "
            "Score the outcome, not production quality. Views are ground truth."
        )
        perf_ref = f"{view_count:,}v / {like_count:,}l"
    else:
        perf_line = f"Performance: {like_count:,} likes (views hidden — {pname} does not expose them)"
        rating_anchor = (
            "100K+ likes=8-9 | 20K-100K=6-7 | 2K-20K=4-5 | <2K=2-3 | <200=0-1. "
            "Likes are ground truth since views are unavailable."
        )
        perf_ref = f"{like_count:,} likes"

    return f"""ROLE: You are writing a machine-readable performance record for a video scoring AI.
Your reader is another AI. Optimize for information density — every token must carry signal.
No prose filler. No hedging. No "it's worth noting that". State mechanisms directly.

SUBJECT: {pname} video | Niche: {niche}
{perf_line}
Platform distribution: {ctx["algorithm"]}
Key signals: {ctx["signals"]}
{ctx["platform_tips"]}

--- DIMENSION SCORING (0-10) ---
Use these exact shorthand codes in your output.

HV (hook_velocity): How fast is the viewer's scroll-reason eliminated?
  10 = premise + open question established within 2s, zero warm-up, viewer MUST stay to resolve
  7  = clear value signal by s3-4, mild pull to continue
  4  = premise eventually clear but no urgency, viewer could scroll with no loss
  0  = opens with creator intro / logo / context-setting / "hey guys" — no hook at all

CF (cut_frequency): Does edit pacing sustain watch-time without losing clarity?
  10 = every cut earns its place, rhythm matches content energy, no dead air anywhere
  7  = active pacing with occasional dead holds that don't hurt
  4  = some cuts but irregular or energy-less, multiple unnecessary holds
  0  = single static shot, >10s holds, zero visual rhythm

TS (text_scannability): Does on-screen text deliver value with sound muted?
  10 = muted viewer loses nothing — kinetic text, key moments highlighted, strategic placement
  7  = helpful text overlays covering most important moments
  4  = text present but only captions audio (no added signal)
  0  = no text, or text that actively clutters without informing

CG (curiosity_gap): Does the opening force a specific unresolved question?
  10 = viewer has a named question by s5 that CANNOT be answered without watching through
  7  = clear interest hook, probable completion, mild open loop
  4  = some interest but no specific question, easy to scroll without loss
  0  = no tension, starts with context or a resolved statement, no loop created

AVS (audio_visual_sync): Does audio amplify and sync with visual information?
  10 = beat drops on cuts, spoken emphasis lands with visual emphasis, sound cues info delivery
  7  = good audio choice, roughly synced, adds energy even if not frame-perfect
  4  = audio is acceptable but generic, ignores the visual rhythm
  0  = audio fights content energy, or voice-over mismatches cuts entirely

LS (loop_seamlessness): Does the ending create rewatch impulse or convert to share/save?
  10 = ending loops back to beginning (implicit rewatch) OR delivers CTA that converts
  7  = satisfying close with weak loop or soft CTA
  4  = clean ending but nothing pulls viewer back or forward
  0  = hard cut / fade-out that signals "done" — maximum scroll-away signal

--- VIRALITY RATING ---
virality_rating is anchored to real performance data, NOT video quality:
{rating_anchor}
Dimension scores must cohere with virality_rating. A 9/10 video cannot have all 2/10 dimensions.
If one dimension clearly drove/killed distribution, let the score spread show it.

--- OUTPUT FIELD RULES ---

what_happens: Pure timestamped description, zero evaluation. 2 sentences max.
  Format: "s0: [what viewer sees/hears]. s[N]-[M]: [events]. Ends: [final frame/action]."
  BAD: "creator effectively demonstrates..." GOOD: "s0: creator holds phone showing 847K views, no audio."

performance_reason: 3 sentences. Top 2 dimensions that drove the outcome. Use HV/CF/TS/CG/AVS/LS codes.
  Each sentence = one causal chain: [element at sN] → [mechanism] → [algorithmic effect on {perf_ref}].

patterns — 6 items each, one per dimension in order [HV, CF, TS, CG, AVS, LS]. Under 15 words per item.
  replicate: "HV: [specific replicable structure]"
  avoid:     "HV: [specific failure pattern + scroll-away signal]"

seed_summary: Dense structured shorthand. No prose. Each line = code + score + mechanism.
  Required format:
  HV:[score] [exact opening format at s0-s2 and whether it eliminates scroll-reason]
  CF:[score] [edit pattern — avg cut interval if notable, energy match or mismatch]
  TS:[score] [text strategy — what shown, when, muted-watchable yes/no]
  CG:[score] [open loop type — question formed, claim made, or gap created]
  AVS:[score] [audio type — trending/original/voiceover, sync quality]
  LS:[score] [ending type — loop/CTA/hard-cut/fade; rewatch signal strength]
  DRIVER: [single element most responsible for {perf_ref} — one causal sentence]
  WEAK: [single biggest drag on score — what a future creator must fix]
  RULE: [name the specific {pname} algorithm signal (watch-time/completion/rewatch/shares) this pattern drives or kills, and the scoring implication — e.g. "CG≥8 in Fitness forces completion → watch-time signal crosses FYP push threshold; score ≥7 when present"]

--- JSON SCHEMA ---
Return ONLY valid JSON. No markdown. No explanation outside the JSON.
{{
  "virality_rating": <0-10>,
  "hook_velocity": <0-10>,
  "cut_frequency": <0-10>,
  "text_scannability": <0-10>,
  "curiosity_gap": <0-10>,
  "audio_visual_sync": <0-10>,
  "loop_seamlessness": <0-10>,
  "what_happens": "<2 timestamped sentences, pure description, zero evaluation>",
  "performance_reason": "<3 sentences, HV/CF/TS/CG/AVS/LS codes, causal chains with timestamps>",
  "patterns": {{
    "replicate": ["HV: <15 words>", "CF: <15 words>", "TS: <15 words>", "CG: <15 words>", "AVS: <15 words>", "LS: <15 words>"],
    "avoid":     ["HV: <15 words>", "CF: <15 words>", "TS: <15 words>", "CG: <15 words>", "AVS: <15 words>", "LS: <15 words>"]
  }},
  "seed_summary": "<HV/CF/TS/CG/AVS/LS lines + DRIVER + WEAK + RULE — structured shorthand, no prose>"
}}"""


async def analyze_seed_video(
    video_path: str,
    platform: str,
    niche: str,
    view_count: Optional[int],
    like_count: int,
) -> dict:
    """Run the seed-analysis prompt against a video. Returns the parsed JSON dict
    on success, or a dict containing an "error" key on any failure. The caller MUST
    treat a missing/invalid "virality_rating" as a failure and not persist the seed.
    """
    try:
        prompt = _build_seed_prompt(platform, niche, view_count, like_count)

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
            ),
        )

        # Delete the Gemini-side file early (Gemini auto-expires after 48h anyway).
        try:
            await client.aio.files.delete(name=uploaded.name)
        except Exception:
            pass  # Non-fatal

        data = json.loads(response.text)
        if not isinstance(data, dict) or "virality_rating" not in data:
            return {"error": "Seed analysis response missing virality_rating."}
        return data

    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse seed analysis as JSON: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
