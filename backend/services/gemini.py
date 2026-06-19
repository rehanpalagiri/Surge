import os
import math
import json
import asyncio
from datetime import datetime, timezone
from google import genai
from google.genai import types
from google.genai.errors import ClientError as _GeminiClientError
from services.niche_weights import get_dimension_hierarchy_block

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
    niche_insight: str | None = None,
    trend_context: str | None = None,
) -> str:
    ctx = _PLATFORM_CONTEXT.get(platform, _PLATFORM_CONTEXT["tiktok"])
    pname = ctx["name"]
    show_seeds = mode in ("thinking", "deep_thinking")
    show_personal = mode in ("thinking", "deep_thinking")  # bio + saved profile context

    high_seeds = high_seeds or []
    low_seeds = low_seeds or []

    # --- Reference context: niche insight block (preferred) or raw seed lists (fallback) ---
    seed_block = ""
    benchmark_block = ""
    if show_seeds:
        if niche_insight:
            # Synthesized pattern intelligence — replaces individual seed injection entirely.
            seed_block = (
                f"NICHE INTELLIGENCE — {pname} / {niche} "
                f"(synthesized from real verified videos in this niche):\n\n"
                + niche_insight.strip()
                + "\n\nWhen scoring this video, apply the patterns above directly. "
                "Name specific connections in analysis_summary: does this video match the "
                "high-performer or low-performer patterns described above?"
            )
        elif high_seeds or low_seeds:
            # Fallback: inject individual seeds when no insight has been generated yet.
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
                "performers below? Name that connection explicitly in analysis_summary.",
            ]
            if high_seeds:
                sections.append(
                    "\n── HIGH PERFORMERS ──\n"
                    + "\n\n".join(fmt_seed(s, "HIGH PERFORMER") for s in high_seeds)
                )
            if low_seeds:
                sections.append(
                    "\n── LOW PERFORMERS ──\n"
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
            benchmark_block = (
                f"\nREAL BENCHMARK DATA ({pname}):\n"
                + "\n".join(bm)
                + "\nUse THESE real numbers to calibrate your scores — not a generic table."
            )

    # --- Trend intelligence block (Thinking/Deep, when available and fresh) ---
    trend_block = ""
    if show_seeds and trend_context and trend_context.strip():
        trend_block = (
            f"\nCURRENT TREND INTELLIGENCE — {pname} / {niche} "
            f"(what has changed in the last 30 days — apply alongside niche intelligence above):\n\n"
            + trend_context.strip()
            + "\n\nWhen scoring this video, check: is it aligned with what is CURRENTLY trending "
            "in this niche, or is it following an outdated format? Reference this explicitly in "
            "analysis_summary when relevant."
        )

    # --- Creator channel profile (Deep only) ---
    profile_perf_block = ""
    if mode == "deep_thinking" and channel_profile:
        profile_perf_block = "\n" + channel_profile.strip() + "\n"

    # --- Per-upload video details ---
    caption_block = (
        f'\nThe creator\'s CAPTION for this video is:\n"""\n{caption.strip()}\n"""'
        if caption and caption.strip()
        else "\nThe creator did not provide a caption — factor that into curiosity_gap and text_scannability."
    )
    bio_block = ""
    profile_block = ""
    if show_personal:
        if bio and bio.strip():
            bio_block = f'\nThe creator\'s PROFILE BIO is:\n"""\n{bio.strip()}\n"""'
        if profile_context and profile_context.strip():
            profile_block = f"\n\nCREATOR PROFILE CONTEXT:\n{profile_context.strip()}"

    is_instagram = platform == "instagram"

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

    projection_schema = '  "projected_verdict": "<honest verdict if they apply the full plan: High potential | Average potential | Needs work>"'

    # Use dynamically-generated weights from the niche insight when available.
    # Fall back to the static niche_weights.py profile when no insight exists yet.
    if niche_insight and show_seeds:
        hierarchy_block = (
            f"DIMENSION HIERARCHY — {niche} on {pname} (data-derived, overrides static defaults):\n"
            "The DIMENSION WEIGHTS section at the end of the NICHE INTELLIGENCE block above "
            "defines the exact scoring hierarchy for this niche. Apply those tier assignments "
            "and percentages when computing overall_score.\n\n"
            "Scoring cap rules derived from the weights above:\n"
            "- Any dimension marked CRITICAL: if its score is ≤ 3, cap overall_score at 4.\n"
            "- HIGH and STANDARD dimensions: weight proportionally per the percentages listed.\n"
            "- LOW dimensions: score independently; a low score here has minimal effect on overall_score.\n\n"
            "improvement_plan ordering: CRITICAL fixes first, then HIGH, then STANDARD, then LOW — "
            "unless a higher-tier dimension is already ≥ 6."
        )
    else:
        hierarchy_block = get_dimension_hierarchy_block(niche, platform)

    return f"""You are an {ctx["analyst_title"]}. Your job is to give BRUTALLY HONEST, unfiltered feedback. Creators come to Surge because they want the truth — not validation. Be direct, be specific, be harsh.
{benchmark_block}
{trend_block}
SCORING RULES (0–10) — read carefully before scoring anything:
- 0–2: Failing. Fundamental problems that guarantee low reach.
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

SIX DIMENSIONS — what each one measures (score each independently):

1. hook_velocity — The first 2.0 seconds ONLY. Is there immediate movement, a visual "pattern interrupt," or on-screen text within the first 60 frames? A static shot of a face talking with no text and no movement in the first 1.5 seconds = 1–3. Text on frame 1 with a dynamic visual = 8–9. Identify EXACTLY what happens in seconds 0–2 and score it on that evidence alone.

2. cut_frequency — Average duration between cuts, zooms, or B-roll inserts across the full video. Any shot held static for more than 3.0 consecutive seconds is a retention hazard. For each such instance, note the approximate timestamp. Score drops for every >3s static hold. Fast edits synced to content energy = 7–9. Long static takes with no movement = 2–4.

3. text_scannability — All on-screen text: size, contrast against the background, and vertical position. Text placed in the bottom 25% of the frame will be covered by the platform's UI overlay (username + description). Text too small to read on a phone at arm's length = fail. Score reflects whether the video is fully watchable on mute. No text at all = 2–3.

4. curiosity_gap — Script architecture in the first 3 seconds. Is there a high-stakes open loop ("This one mistake costs creators thousands..." / "I found something that changes everything about...") that makes the viewer need to keep watching? Or does the creator open with an introduction ("Hey guys, today I'm going to talk about...") or slow context-setting? Introduction or context trap = 1–2. Punchy open loop with a clear stakes claim = 8–9.

5. audio_visual_sync — Do visual cuts align with audio peaks, beat drops, sound effects (whoosh, pop, riser), or speech-emphasis moments? Un-synced edits feel amateur and trigger accidental scrolling. For each major mis-sync, note the approximate timestamp. Tight sync throughout = 8–9. Obvious lag or random cuts with no audio relationship = 2–4.

6. loop_seamlessness — The relationship between the LAST 2 seconds and the FIRST 2 seconds. Does the ending create a seamless re-entry — an open-ended sentence that calls back to the opening, or a question that gets answered by watching again? Or does it signal scroll-away ("Thanks for watching", "Like and subscribe", hard cut to black, explicit sign-off)? Scroll-away ending = 1–3. Seamless loop trigger = 8–9.

{hierarchy_block}

verdict rules (apply these exactly, no exceptions):
- "High potential": overall_score ≥ 7 AND at least one of hook_velocity or curiosity_gap is ≥ 5.
- "Average potential": overall_score is 5 or 6, OR overall_score ≥ 7 but BOTH hook_velocity < 5 AND curiosity_gap < 5.
- "Needs work": overall_score ≤ 4.

FEEDBACK QUALITY STANDARD — every improvement must be hyper-specific:
- Reference the EXACT moment in the video (e.g. "At 0–3 seconds", "Around the 8-second mark", "The final line").
- Name the EXACT problem visible in this video (e.g. "static talking head with no movement or text", "shot held for 4 seconds with no cut at 0:12").
- Give an EXACT fix the creator can implement TODAY — not "improve your hook" but "Add a bold white text overlay in the first 2 seconds that reads something like: 'The mistake every [niche] creator makes'".
- For captions: rewrite the actual caption word-for-word. Don't say "make it more engaging" — show the specific better version.
- For pacing: name the exact timestamp where a static hold exceeds 3 seconds and say what to cut or insert there.
- Never write advice that applies to every video. Every sentence must be about THIS video specifically.

ANALYSIS INSTRUCTIONS:
- Watch the entire video before scoring anything.
- Score each dimension independently. A great hook_velocity does not raise cut_frequency.
- When a dimension has a clear flaw, reference the EXACT timestamp or moment ("at 0:04", "the final line", "frames 0–1.5").
- For strengths: only list things that genuinely work. If nothing stands out, say so with one honest entry.
- For improvements: be blunt. Name the specific problem visible in THIS video. No generic advice.
- Every "problem", "fix", and "example" in the improvement_plan must reference something actually seen in THIS video.
- "example" must show a concrete before → after.
- Build the improvement_plan ordered by IMPACT ON REACH for this specific niche (see DIMENSION HIERARCHY above — CRITICAL dimensions almost always rank first for this niche). Priority 1 = the fix that would most increase reach for a {niche} video. Provide 3–6 items.
- For "caption_rewrite": rewrite their actual caption to maximize {pname} performance. If they gave no caption, write one from scratch that fits the video.
- For "hook_rewrite": identify what exists in the first 1–2 seconds — if there's spoken dialogue, rewrite the first sentence; if there's on-screen text, rewrite that text; if neither exists, write what on-screen text they should ADD to frame 1. Always state what was there originally and why you changed it.
- "projected_verdict" is your honest assessment of the verdict IF the creator applies every fix in the plan.

Return ONLY valid JSON with exactly this structure:
{{
  "overall_score": <0-10, computed using the DIMENSION HIERARCHY rules above — NOT a simple average>,
  "hook_velocity": <0-10>,
  "cut_frequency": <0-10>,
  "text_scannability": <0-10>,
  "curiosity_gap": <0-10>,
  "audio_visual_sync": <0-10>,
  "loop_seamlessness": <0-10>,
  "strengths": ["<specific genuine strength 1>", "<specific genuine strength 2>"],
  "improvements": ["<blunt specific improvement 1>", "<blunt specific improvement 2>", "<blunt specific improvement 3>"],
  "verdict": "<apply the verdict rules above exactly: High potential | Average potential | Needs work>",
  "analysis_summary": "<3 sentences: (1) the single biggest barrier to reach, named with the exact timestamp or moment it fails; (2) the single most genuine strength, or an honest admission if there are none; (3) what this video needs most to have a real shot>",
  "improvement_plan": [
    {{
      "area": "<Hook Velocity | Cut Frequency | Text Scannability | Curiosity Gap | Audio-Visual Sync | Loop Seamlessness>",
      "priority": <1 = highest impact first>,
      "current_score": <0-10>,
      "problem": "<specific issue visible in THIS video, with timestamp if applicable>",
      "fix": "<specific actionable step — name exactly what to add, change, or cut and where>",
      "example": "<concrete before → after example using this video's actual content>"
    }}
  ],
  "caption_rewrite": "<rewritten caption optimized for {pname}>",
  "hook_rewrite": "<specific rewrite of the first 1-2 seconds — state what was there and what to change it to>",
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
    niche_insight: str | None = None,
    trend_context: str | None = None,
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
            niche_insight=niche_insight,
            trend_context=trend_context,
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
        "overall_score": 0,
        "hook_velocity": 0,
        "cut_frequency": 0,
        "text_scannability": 0,
        "curiosity_gap": 0,
        "audio_visual_sync": 0,
        "loop_seamlessness": 0,
        "strengths": [],
        "improvements": [],
        "verdict": "Needs work",
        "analysis_summary": f"Analysis failed: {msg}",
        "improvement_plan": [],
        "caption_rewrite": "",
        "hook_rewrite": "",
        "projected_verdict": "",
        "error": msg,
    }
