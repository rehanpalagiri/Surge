import os
import math
import json
import asyncio
from datetime import datetime, timezone
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def _recency_multiplier(seed) -> float:
    """Exponential decay based on how old the seed video is.
    Uses posted_at if set, otherwise falls back to created_at.
    Half-life ≈ 42 days → a 90-day-old video scores ~0.14×, a 180-day-old ~0.02×.
    Very recent videos (< 7 days) are capped at 1.0 so they aren't over-weighted."""
    now = datetime.now(timezone.utc)
    ref = seed.posted_at or seed.created_at
    if ref is None:
        return 0.1  # unknown age → treat as old
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - ref).total_seconds() / 86400)
    return min(1.0, math.exp(-age_days / 60))


_PLATFORM_CONTEXT = {
    "tiktok": {
        "name": "TikTok",
        "algorithm": "For You Page (FYP)",
        "analyst_title": "elite TikTok performance analyst",
        "signals": "watch time, replays, shares, comments, follows-from-video, and FYP distribution signals",
        "platform_tips": (
            "TikTok-specific factors: hook must land in the first 1–2 seconds to stop the scroll; "
            "trending sounds boost FYP distribution; duet/stitch potential adds reach; "
            "TikTok SEO (keywords in caption + spoken words) affects search discovery."
        ),
    },
    "instagram": {
        "name": "Instagram",
        "algorithm": "Explore page and Reels tab",
        "analyst_title": "elite Instagram Reels performance analyst",
        "signals": "saves, shares, watch-through rate, profile visits, and Explore/Reels feed distribution",
        "platform_tips": (
            "Instagram Reels-specific factors: aesthetic quality and visual polish matter more than TikTok; "
            "saves and shares are the highest-weight signals for the Explore algorithm; "
            "on-screen text and captions are critical since many users watch without sound; "
            "hashtag strategy (mix of niche + broad) affects Explore reach; "
            "the first frame must be visually compelling as a static thumbnail in the grid."
        ),
    },
}


def _build_system_prompt(
    niche: str,
    seed_examples: list,
    caption: str = "",
    bio: str = "",
    platform: str = "tiktok",
    profile_context: str = "",
) -> str:
    # Prefer examples from the same niche; fall back to the global pool when the
    # niche isn't seeded enough yet (so the prompt is never empty or too sparse).
    niche_seeds = [s for s in seed_examples if s.niche == niche]
    use_niche = len(niche_seeds) >= 6
    pool = niche_seeds if use_niche else seed_examples

    # Sort by recency-weighted view count so that newer TikToks surface first.
    # Formula: view_count × recency_multiplier — recent videos with average views
    # rank above old videos with high views, reflecting current trend signals.
    sorted_pool = sorted(
        pool,
        key=lambda s: s.view_count * _recency_multiplier(s),
        reverse=True,
    )
    top = sorted_pool[:10]
    bottom = [s for s in reversed(sorted_pool) if s not in top][:10]

    def fmt(s):
        notes = f" | Notes: {s.notes}" if s.notes else ""
        ref = s.posted_at or s.created_at
        date_str = f" | Posted: {ref.strftime('%b %Y')}" if ref else ""
        return (
            f"  - Niche: {s.niche} | Views: {s.view_count:,}"
            f" | Likes: {s.like_count:,}{date_str}{notes}"
        )

    top_str = "\n".join(fmt(s) for s in top) or "  (no data yet)"
    bottom_str = "\n".join(fmt(s) for s in bottom) or "  (no data yet)"

    ctx = _PLATFORM_CONTEXT.get(platform, _PLATFORM_CONTEXT["tiktok"])
    pname = ctx["name"]

    # Label by niche only when we're actually using same-niche examples.
    if use_niche:
        top_heading = f"TOP PERFORMING {niche.upper()} {pname.upper()} VIDEOS"
        bottom_heading = f"WORST PERFORMING {niche.upper()} {pname.upper()} VIDEOS"
    else:
        top_heading = f"TOP PERFORMING {pname.upper()} VIDEOS FROM OUR DATABASE"
        bottom_heading = f"WORST PERFORMING {pname.upper()} VIDEOS FROM OUR DATABASE"

    caption_block = (
        f'\nThe creator\'s CAPTION for this video is:\n"""\n{caption.strip()}\n"""'
        if caption and caption.strip()
        else "\nThe creator did not provide a caption — factor that into the caption_score."
    )
    bio_block = (
        f'\nThe creator\'s PROFILE BIO is:\n"""\n{bio.strip()}\n"""'
        if bio and bio.strip()
        else f"\nThe creator did not provide a profile bio."
    )
    profile_block = (
        f"\n\nCREATOR PROFILE CONTEXT:\n{profile_context.strip()}"
        if profile_context and profile_context.strip()
        else ""
    )

    return f"""You are an {ctx["analyst_title"]} with years of experience identifying viral content patterns across all niches. You have studied thousands of videos and can predict performance with high accuracy by analyzing hook strength, pacing, audio choices, captions, and trend alignment.

{top_heading}:
{top_str}

{bottom_heading}:
{bottom_str}

The user's video is a **{pname} Reel/video** in the **{niche}** niche.
{caption_block}
{bio_block}
{profile_block}

PLATFORM-SPECIFIC CONTEXT ({pname}):
The primary distribution surface is the {ctx["algorithm"]}. The key engagement signals are: {ctx["signals"]}.
{ctx["platform_tips"]}

When scoring caption_score, judge the actual caption text above (hook words, hashtags, call-to-action, length) specifically for {pname}'s caption norms. Consider whether the caption and bio reinforce the video's topic and niche, and whether the bio would convert a viewer into a follower on {pname}.

Analyze the provided video carefully and be SPECIFIC and ACTIONABLE — no generic advice. Every suggestion must be tailored to how the **{pname} algorithm** rewards content in {niche}.

Build the "improvement_plan" by targeting this video's WEAKEST scores first: each item's "area" should correspond to a low score above, "priority" 1 is the single highest-impact change, and items must be ordered by impact (priority 1 first). Every "problem", "fix", and "example" must be specific to THIS video — never generic. The "example" must show a concrete before → after. Provide 3–5 plan items.

For "caption_rewrite", rewrite the creator's caption optimized for {pname} (if no caption was given, write one from scratch that fits the video and {pname}'s style). For "hook_rewrite", rewrite the first 1–2 seconds of the video (spoken line or on-screen text). "projected_verdict" and "projected_views" are your honest estimate of how this video would perform on {pname} IF the creator applied the full plan.

Return ONLY valid JSON with exactly this structure:
{{
  "overall_score": <0-100>,
  "hook_strength": <0-100>,
  "pacing_score": <0-100>,
  "audio_score": <0-100>,
  "caption_score": <0-100>,
  "trend_alignment": <0-100>,
  "predicted_views": "<range like '10k-50k views'>",
  "strengths": ["<specific strength 1>", "<specific strength 2>", "<specific strength 3>"],
  "improvements": ["<specific improvement 1>", "<specific improvement 2>", "<specific improvement 3>"],
  "verdict": "<exactly one of: High potential | Average potential | Needs work>",
  "analysis_summary": "<2-3 sentence overall summary>",
  "improvement_plan": [
    {{
      "area": "<Hook | Pacing | Audio | Caption | Trend | Visuals>",
      "priority": <1 = highest impact first>,
      "current_score": <0-100>,
      "problem": "<specific issue with THIS video>",
      "fix": "<specific actionable step>",
      "example": "<concrete before/after example>"
    }}
  ],
  "caption_rewrite": "<punched-up rewrite of their caption; suggest one if none given>",
  "hook_rewrite": "<specific rewrite of the first 1-2 seconds>",
  "projected_verdict": "<verdict if they apply the plan>",
  "projected_views": "<projected view range if applied>"
}}"""


async def analyze_video(
    video_path: str,
    niche: str,
    seed_examples: list,
    caption: str = "",
    bio: str = "",
    platform: str = "tiktok",
    profile_context: str = "",
) -> dict:
    try:
        prompt = _build_system_prompt(niche, seed_examples, caption, bio, platform, profile_context)

        uploaded = await client.aio.files.upload(file=video_path)

        # Poll until the file is ACTIVE (processed and ready to use).
        max_wait = 120
        waited = 0
        while uploaded.state.name != "ACTIVE":
            if uploaded.state.name == "FAILED":
                return _error_dict("Gemini failed to process the video file.")
            if waited >= max_wait:
                return _error_dict("Video processing timed out.")
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

        # Delete the uploaded file immediately — Gemini auto-purges after 48h,
        # but we clean up early to avoid storing users' video data longer than needed.
        try:
            await client.aio.files.delete(name=uploaded.name)
        except Exception:
            pass  # Non-fatal; Gemini will expire it automatically

        return json.loads(response.text)

    except json.JSONDecodeError as e:
        return _error_dict(f"Failed to parse Gemini response as JSON: {e}")
    except Exception as e:
        return _error_dict(str(e))


def _error_dict(msg: str) -> dict:
    return {
        "overall_score": 0,
        "hook_strength": 0,
        "pacing_score": 0,
        "audio_score": 0,
        "caption_score": 0,
        "trend_alignment": 0,
        "predicted_views": "Unknown",
        "strengths": [],
        "improvements": [],
        "verdict": "Needs work",
        "analysis_summary": f"Analysis failed: {msg}",
        "improvement_plan": [],
        "caption_rewrite": "",
        "hook_rewrite": "",
        "projected_verdict": "",
        "projected_views": "",
        "error": msg,
    }
