import os
import math
import json
import asyncio
from datetime import datetime, timezone
from google import genai
from google.genai import types
from google.genai.errors import ClientError as _GeminiClientError

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


# Mode-specific guidance for the predicted_views field (TikTok). {pname} filled at build time.
_PREDICTED_VIEWS_GUIDANCE = {
    "quick": (
        "For predicted_views: you have NO reference library for this run — rely on your "
        "general training knowledge of {pname}. Most videos from creators who haven't "
        "broken through land under 5,000 views. Give a realistic range and err LOW."
    ),
    "thinking": (
        "For predicted_views: anchor to the GLOBAL PERFORMANCE REFERENCE and REAL BENCHMARK "
        "DATA above. Most videos land far closer to the low-performer range than the high. "
        "Never exceed the high-performer peak unless the video is clearly exceptional. Err LOW."
    ),
    "deep_thinking": (
        "For predicted_views: anchor primarily to this creator's VERIFIED history above, and "
        "also use the global benchmark data when shown. If their typical video gets ~800 views, "
        "require clear breakout signals in THIS video to predict meaningfully higher. Err LOW."
    ),
}

# Mode-specific guidance for predicted_likes (Instagram — views are hidden by the platform).
_PREDICTED_LIKES_GUIDANCE = {
    "quick": (
        "For predicted_likes: you have NO reference library for this run — rely on your "
        "general training knowledge of Instagram Reels. Most Reels from creators who haven't "
        "broken through get under 500 likes. Give a realistic range and err LOW."
    ),
    "thinking": (
        "For predicted_likes: anchor to the GLOBAL PERFORMANCE REFERENCE and REAL BENCHMARK "
        "DATA above. Most Reels land far closer to the low-performer range. "
        "Never exceed the high-performer peak unless the video is clearly exceptional. Err LOW."
    ),
    "deep_thinking": (
        "For predicted_likes: anchor primarily to this creator's VERIFIED history above, and "
        "also use the global benchmark data. If their typical Reel gets ~200 likes, "
        "require clear breakout signals in THIS video to predict meaningfully higher. Err LOW."
    ),
}


def _seed_summary(s) -> str:
    """Pull the AI-written seed_summary out of a seed's stored gemini_analysis JSON.
    Never raises — returns '' if the field is missing or the JSON is malformed."""
    try:
        data = json.loads(s.gemini_analysis) if s.gemini_analysis else {}
        if isinstance(data, dict):
            return (data.get("seed_summary") or "").strip()
    except (ValueError, TypeError):
        pass
    return ""


def select_seed_examples(pool_for_platform: list, niche: str):
    """Bucket seeds into HIGH (rating >= 6) and LOW (rating <= 4) performers using the
    Gemini virality rating. Disjoint thresholds make overlap impossible; rating == 5 or
    None is dormant (never injected — we don't seed average videos). Recency is only an
    intra-rating tiebreaker, so it can never move a video between buckets.

    Prefers same-niche seeds, falling back to the full platform pool when the niche
    isn't seeded enough yet. Returns (high[:10], low[:10]).
    """
    niche_seeds = [s for s in pool_for_platform if s.niche == niche]
    pool = niche_seeds if len(niche_seeds) >= 6 else pool_for_platform
    high = [s for s in pool if s.rating is not None and s.rating >= 6]
    low = [s for s in pool if s.rating is not None and s.rating <= 4]
    # Recency tiebreaker. Instagram seeds have view_count=None — use like_count as proxy.
    def _score(s):
        base = s.view_count if s.view_count is not None else (s.like_count * 10)
        return base * _recency_multiplier(s)

    high.sort(key=lambda s: (s.rating, _score(s)), reverse=True)
    low.sort(key=lambda s: (s.rating, _score(s)))
    return high[:10], low[:10]


def _build_system_prompt(
    niche: str,
    high_seeds: list,
    low_seeds: list,
    caption: str = "",
    bio: str = "",
    platform: str = "tiktok",
    profile_context: str = "",
    channel_profile: str | None = None,
    mode: str = "quick",
    niche_raw: str = "",
    creator_like_baseline: dict | None = None,
) -> str:
    ctx = _PLATFORM_CONTEXT.get(platform, _PLATFORM_CONTEXT["tiktok"])
    pname = ctx["name"]
    show_seeds = mode in ("thinking", "deep_thinking")
    show_personal = mode in ("thinking", "deep_thinking")  # bio + saved profile context

    high_seeds = high_seeds or []
    low_seeds = low_seeds or []

    # --- Global seed reference + numeric benchmark (Thinking / Deep, when present) ---
    seed_block = ""
    benchmark_block = ""
    if show_seeds and (high_seeds or low_seeds):
        def fmt_seed(s, label):
            summary = _seed_summary(s) or "(no summary available)"
            views_str = f"{s.view_count:,} views | " if s.view_count is not None else ""
            return (
                f"[{label} | {s.niche} | {views_str}"
                f"{s.like_count:,} likes | Rating {s.rating}/10]\n{summary}"
            )

        sections = [
            f"GLOBAL PERFORMANCE REFERENCE ({pname} — real videos with verified results).",
            "When you spot a pattern in the user's video, ask: does it match the HIGH or LOW "
            "performers below? Name that connection explicitly in analysis_summary. Reward "
            "HIGH-PERFORMER patterns, penalize LOW-PERFORMER ones. If it matches neither, say so.",
        ]
        if high_seeds:
            sections.append(
                "\n── HIGH PERFORMERS — what made these succeed ──\n"
                + "\n\n".join(fmt_seed(s, "HIGH PERFORMER") for s in high_seeds)
            )
        if low_seeds:
            sections.append(
                "\n── LOW PERFORMERS — what caused these to fail ──\n"
                + "\n\n".join(fmt_seed(s, "LOW PERFORMER") for s in low_seeds)
            )
        seed_block = "\n".join(sections)

        bm = []
        if high_seeds:
            hv = [s.view_count for s in high_seeds if s.view_count is not None]
            hl = [s.like_count for s in high_seeds]
            if hv:
                bm.append(
                    f"  High performers: avg {sum(hv) // len(hv):,} views / "
                    f"{sum(hl) // len(hl):,} likes (peak {max(hv):,} views)"
                )
            else:
                bm.append(
                    f"  High performers: avg {sum(hl) // len(hl):,} likes "
                    f"(peak {max(hl):,} likes — views not available for this platform)"
                )
        if low_seeds:
            lv = [s.view_count for s in low_seeds if s.view_count is not None]
            ll = [s.like_count for s in low_seeds]
            if lv:
                bm.append(
                    f"  Low performers: avg {sum(lv) // len(lv):,} views / "
                    f"{sum(ll) // len(ll):,} likes"
                )
            else:
                bm.append(
                    f"  Low performers: avg {sum(ll) // len(ll):,} likes"
                )
        anchor_field = "predicted_likes" if platform == "instagram" else "predicted_views"
        benchmark_block = (
            f"\nREAL BENCHMARK DATA ({pname}):\n"
            + "\n".join(bm)
            + f"\nUse THESE real numbers to anchor {anchor_field} — not a generic table."
        )

    # --- Creator channel profile (Deep only) ---
    profile_perf_block = ""
    if mode == "deep_thinking" and channel_profile:
        profile_perf_block = "\n" + channel_profile.strip() + "\n"

    # --- Per-upload video details ---
    caption_block = (
        f'\nThe creator\'s CAPTION for this video is:\n"""\n{caption.strip()}\n"""'
        if caption and caption.strip()
        else "\nThe creator did not provide a caption — factor that into the caption_score."
    )
    bio_block = ""
    profile_block = ""
    if show_personal:
        if bio and bio.strip():
            bio_block = f'\nThe creator\'s PROFILE BIO is:\n"""\n{bio.strip()}\n"""'
        if profile_context and profile_context.strip():
            profile_block = f"\n\nCREATOR PROFILE CONTEXT:\n{profile_context.strip()}"

    is_instagram = platform == "instagram"
    if is_instagram:
        predicted_guidance = _PREDICTED_LIKES_GUIDANCE.get(
            mode, _PREDICTED_LIKES_GUIDANCE["quick"]
        )
    else:
        predicted_guidance = _PREDICTED_VIEWS_GUIDANCE.get(
            mode, _PREDICTED_VIEWS_GUIDANCE["quick"]
        ).format(pname=pname)

    # Canonical niche drives seed matching; the creator's own words add
    # specificity for the model. Cap raw text so an essay can't bloat the prompt.
    niche_line = f"The user's video is a **{pname} video** in the **{niche}** niche."
    raw = (niche_raw or "").strip()[:80]
    if raw and raw.lower() != niche.lower():
        niche_line = (
            f"The user's video is a **{pname} video** in the **{niche}** niche "
            f'(creator describes their content as: "{raw}").'
        )

    if creator_like_baseline and creator_like_baseline.get("sample_count", 0) >= 2:
        ml = creator_like_baseline["median_likes"]
        n = creator_like_baseline["sample_count"]
        low_threshold = max(0, ml // 4)
        mid_high = ml * 3
        breakout = ml * 8
        calibration_block = (
            f"CALIBRATION — PERSONALISED TO THIS CREATOR (based on {n} verified post(s)):\n"
            f"Their videos typically get ~{ml:,} likes.\n"
            f"Score RELATIVE TO THEIR OWN BASELINE — not against industry averages:\n"
            f"- 3–4: Underperforming for them (~{low_threshold:,} likes or fewer).\n"
            f"- 5: About what they normally get (~{ml:,} likes).\n"
            f"- 6–7: Noticeably above their typical (~{ml * 2:,}–{mid_high:,} likes).\n"
            f"- 8–9: A breakout for this creator (~{breakout:,}+ likes — rare for their account).\n"
            f"- 10: Never give this.\n"
            f"A creator with a {ml:,}-like baseline scoring 5 is doing fine for THEM — "
            f"don't penalise a micro-creator for having a smaller audience."
        )
    else:
        calibration_block = (
            "CALIBRATION (internalize this before scoring):\n"
            "- A random person's first video upload = 2–3.\n"
            "- A creator who posts regularly but hasn't broken through = 4–5.\n"
            + (
                "- A Reel that gets 2k–10k likes organically = 6–7.\n"
                "- A Reel that blows up (50k+ likes) = 8–9.\n"
                if is_instagram else
                "- A video that gets 50k–200k views organically = 6–7.\n"
                "- A video that blows up (500k+) = 8–9.\n"
            )
            + "- When in doubt, score LOWER. Inflated scores are useless. The creator already knows if their video was great — they're here because it probably wasn't."
        )

    projection_instruction = (
        "- \"projected_verdict\" and \"projected_likes\" should be your honest estimate IF the creator applies every fix — don't be overly optimistic."
        if is_instagram else
        "- \"projected_verdict\" and \"projected_views\" should be your honest estimate IF the creator applies every fix — don't be overly optimistic."
    )

    prediction_schema = (
        f'  "predicted_likes": "<realistic like range. {predicted_guidance} When in doubt, predict LESS.>",'
        if is_instagram else
        f'  "predicted_views": "<realistic view range. {predicted_guidance} When in doubt, predict LESS.>",\n'
        f'  "predicted_likes": "<realistic like range, typically 3–10% of predicted views. Err LOW.>",'
    )

    projection_schema = (
        '  "projected_verdict": "<honest verdict if they apply the full plan>",\n'
        '  "projected_likes": "<realistic projected like range after fixes. Err LOW.>"'
        if is_instagram else
        '  "projected_verdict": "<honest verdict if they apply the full plan>",\n'
        '  "projected_views": "<realistic projected range after fixes. Only approach top-performer territory if the fixes would genuinely transform the video. Most creators still land well below top-performer numbers even after improvements.>",\n'
        '  "projected_likes": "<realistic like range after fixes. Err LOW.>"'
    )

    return f"""You are an {ctx["analyst_title"]}. Your job is to give BRUTALLY HONEST, unfiltered feedback. Creators come to Surge because they want the truth — not validation. Be direct, be specific, be harsh.
{benchmark_block}

SCORING RULES (0–10) — read carefully before scoring anything:
- 0–2: Failing. Fundamental problems. Hook doesn't work, content is unwatchable or painfully generic.
- 3–4: Poor to below-average. Some effort visible but major problems in multiple areas. Most first-time creators land here.
- 5: Dead average. Forgettable. Nothing wrong enough to fail, nothing right enough to succeed. Most uploads from regular creators land here.
- 6: Slightly above average. One or two genuine strengths but still has clear weaknesses.
- 7: Solid. Real potential, likely to get decent reach if a few things are fixed.
- 8: Strong. Genuinely competitive content. Only minor polish needed.
- 9: Near-viral quality. Rare. Give this only when the video is clearly elite.
- 10: Exceptional. Do not give this. Ever.

{calibration_block}
{profile_perf_block}{seed_block}

{niche_line}
{caption_block}{bio_block}{profile_block}

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
- {projection_instruction}
- {predicted_guidance}

Return ONLY valid JSON with exactly this structure:
{{
  "overall_score": <0-10>,
  "hook_strength": <0-10>,
  "pacing_score": <0-10>,
  "audio_score": <0-10>,
  "caption_score": <0-10>,
  "trend_alignment": <0-10>,
{prediction_schema}
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
{projection_schema}
}}"""


async def analyze_video(
    video_path: str,
    niche: str,
    high_seeds: list,
    low_seeds: list,
    caption: str = "",
    bio: str = "",
    platform: str = "tiktok",
    profile_context: str = "",
    channel_profile: str | None = None,
    mode: str = "quick",
    niche_raw: str = "",
    creator_like_baseline: dict | None = None,
) -> dict:
    try:
        prompt = _build_system_prompt(
            niche,
            high_seeds,
            low_seeds,
            caption,
            bio,
            platform,
            profile_context,
            channel_profile,
            mode,
            niche_raw=niche_raw,
            creator_like_baseline=creator_like_baseline,
        )

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

    except _GeminiClientError as e:
        if e.code in (429, 403):
            raise  # quota or bad key — router returns 503 without storing broken data
        # Any other API error (400/404/500/503, etc.) degrades gracefully — without
        # this return the function would fall through to None and crash the router.
        return _error_dict(f"Gemini API error ({e.code}): {e}")
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
        "predicted_likes": "Unknown",
        "strengths": [],
        "improvements": [],
        "verdict": "Needs work",
        "analysis_summary": f"Analysis failed: {msg}",
        "improvement_plan": [],
        "caption_rewrite": "",
        "hook_rewrite": "",
        "projected_verdict": "",
        "projected_views": "",
        "projected_likes": "",
        "error": msg,
    }
