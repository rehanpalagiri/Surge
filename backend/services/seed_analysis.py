"""Seed-analysis pipeline.

When an admin uploads a reference ("seed") video, we send it to Gemini ONCE to
produce a causal, AI-consumption-only performance writeup. That JSON is stored on
the seed row (`gemini_analysis`) and the extracted `virality_rating` becomes the
seed's `rating`. The video file itself is deleted afterwards — the JSON is the
durable artifact, read back into the live scoring prompt for Thinking/Deep modes.

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

    # Instagram hides view counts — anchor on likes only when view_count is None.
    if view_count is not None:
        perf_line = f"It received {view_count:,} views and {like_count:,} likes."
        rating_anchor = (
            "virality_rating: anchor directly to the view/like count as evidence. "
            "2M views = proof of 8–9. 800 views = proof of 1–3. Score what the data confirms."
        )
        perf_reason_ref = f"exactly why this got {view_count:,} views and {like_count:,} likes"
    else:
        perf_line = (
            f"It received {like_count:,} likes "
            f"(view count not available — {pname} does not expose it publicly)."
        )
        rating_anchor = (
            "virality_rating: anchor to the like count as evidence since views are unavailable. "
            "18M likes = proof of 8–9. 500 likes = proof of 1–3. Score what the data confirms."
        )
        perf_reason_ref = f"exactly why this got {like_count:,} likes"

    return f"""You are building a performance reference library for a video scoring AI.
This analysis is NOT user-facing — it will be read by another AI instance when
scoring new creator videos. Write everything with that reader in mind: specific,
causal, pattern-focused. Never use vague descriptors.

This is a {pname} video in the {niche} niche.
{perf_line}

PLATFORM CONTEXT ({pname}):
Distribution surface: {ctx["algorithm"]}
Key engagement signals: {ctx["signals"]}
{ctx["platform_tips"]}

Your job: explain exactly WHY it performed this way. What specific elements caused
these results? What should a future AI look for — or warn against — when it sees
similar patterns in a new video?

SCORING RULES (0–10):
- {rating_anchor}
- hook_strength: did the first 1–3 seconds eliminate the viewer's reason to scroll?
- pacing_score: do cuts and energy sustain watch time to the end?
- audio_score: does the sound serve the content or fight it?
- visual_score: framing, lighting, on-screen text, production quality.
- trend_alignment: is this riding a current format, sound, or topic trend on {pname}?

SEED SUMMARY RULES — most important field, target 150 words:
- Written entirely for AI consumption — never for a human reader.
- Lead with the single most causally important factor driving performance.
- Be precise: not "good hook" but "creator displays the end result in frame 1
  before any explanation, removing the viewer's reason to scroll".
- Explain causality: not just what happened but why it produced this specific
  outcome given {pname}'s algorithm.
- Close with 1–2 sentences telling a future AI exactly what to look for or flag
  when it sees similar patterns in a new video.
- Do NOT write a "high/low performer" label — that is applied separately.

Return ONLY valid JSON with exactly this structure:
{{
  "virality_rating": <0-10>,
  "hook_strength": <0-10>,
  "pacing_score": <0-10>,
  "audio_score": <0-10>,
  "visual_score": <0-10>,
  "trend_alignment": <0-10>,
  "what_happens": "<2-3 sentences: literal events start to finish, no evaluation>",
  "performance_reason": "<3-4 sentences: causal explanation for {perf_reason_ref}. Name the elements that drove or killed distribution.>",
  "patterns": {{
    "replicate": ["<pattern worth copying, as an instruction>", "<pattern 2>"],
    "avoid": ["<pattern to warn against, as a flag>", "<pattern 2>"]
  }},
  "seed_summary": "<150 words, AI-consumption only, causal and self-contained.>"
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
