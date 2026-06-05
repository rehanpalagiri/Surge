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

    return f"""You are an {ctx["analyst_title"]}. Your job is to give BRUTALLY HONEST, unfiltered feedback. Creators come to Surge because they want the truth — not validation. Be direct, be specific, be harsh if the video deserves it.

SCORING RULES (0–10):
- 1–3: Poor. Significant fundamental problems. Unlikely to get meaningful reach.
- 4–5: Below average. Some redeeming qualities but major issues holding it back.
- 6–7: Solid. Above average with real potential. A few things to fix.
- 8–9: Strong. Genuinely good content with minor improvements needed.
- 10: Exceptional. Rare. Do not give 10 unless the video is truly outstanding.
The AVERAGE creator video scores 4–5 overall. Do NOT inflate scores to be nice. If something deserves a 2, give it a 2. Dishonest scores help nobody.

{top_heading}:
{top_str}

{bottom_heading}:
{bottom_str}

The user's video is a **{pname} video** in the **{niche}** niche.
{caption_block}
{bio_block}
{profile_block}

PLATFORM CONTEXT ({pname}):
Distribution surface: {ctx["algorithm"]}. Key signals: {ctx["signals"]}.
{ctx["platform_tips"]}

ANALYSIS INSTRUCTIONS:
- Watch the entire video before scoring anything.
- Score each dimension independently. A great hook does not raise the pacing score.
- For caption_score: judge the actual caption text — hook words, hashtags, CTA, length — against {pname} norms. If no caption was provided, score it as 1 (missing = a real problem).
- For strengths: only list things that genuinely work. If nothing stands out, say so with one honest entry.
- For improvements: be blunt. Name the specific problem visible in THIS video. No generic advice.
- Every "problem", "fix", and "example" in the improvement_plan must reference something actually seen in THIS video.
- "example" must show a concrete before → after.
- Build the improvement_plan ordered by impact (priority 1 = highest impact). Target the weakest areas first. Provide 3–5 items.
- For "caption_rewrite": rewrite their actual caption to maximize {pname} performance. If they gave no caption, write one from scratch that fits the video.
- For "hook_rewrite": rewrite the exact first spoken line or on-screen text to stop the scroll.
- "projected_verdict" and "projected_views" should be your honest estimate IF the creator applies every fix — don't be overly optimistic.

Return ONLY valid JSON with exactly this structure:
{{
  "overall_score": <0-10>,
  "hook_strength": <0-10>,
  "pacing_score": <0-10>,
  "audio_score": <0-10>,
  "caption_score": <0-10>,
  "trend_alignment": <0-10>,
  "predicted_views": "<realistic range like '500-2k views' or '50k-200k views'>",
  "strengths": ["<specific genuine strength 1>", "<specific genuine strength 2>"],
  "improvements": ["<blunt specific improvement 1>", "<blunt specific improvement 2>", "<blunt specific improvement 3>"],
  "verdict": "<exactly one of: High potential | Average potential | Needs work>",
  "analysis_summary": "<2-3 sentences: be direct, say what works and what doesn't without softening it>",
  "improvement_plan": [
    {{
      "area": "<Hook | Pacing | Audio | Caption | Trend | Visuals>",
      "priority": <1 = highest impact first>,
      "current_score": <0-10>,
      "problem": "<specific issue visible in THIS video>",
      "fix": "<specific actionable step tailored to this video>",
      "example": "<concrete before → after example>"
    }}
  ],
  "caption_rewrite": "<rewritten caption optimized for {pname}>",
  "hook_rewrite": "<specific rewrite of the first 1-2 seconds>",
  "projected_verdict": "<honest verdict if they apply the full plan>",
  "projected_views": "<realistic projected range after fixes>"
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
        "overall_score": 0,   # 0–10 scale
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
