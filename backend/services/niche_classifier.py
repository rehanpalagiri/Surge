"""Maps a creator's free-text niche description to one of the 20 canonical
niches used for seed matching. The canonical label keeps seed bucketing
deterministic; the raw text still goes to the analysis prompt for specificity.
"""
import asyncio
import json

from google.genai import types

from services.gemini import client

CANONICAL_NICHES = [
    "Fitness & Gym",
    "Comedy & Skits",
    "Food & Cooking",
    "Fashion & Style",
    "Beauty & Makeup",
    "Education & Tutorials",
    "Gaming",
    "Music & Dance",
    "Tech & Gadgets",
    "Finance & Investing",
    "Health & Wellness",
    "Travel & Adventure",
    "Lifestyle & Vlogs",
    "Motivation & Mindset",
    "Sports & Athletics",
    "Relationships & Dating",
    "Art & Creativity",
    "Business & Entrepreneurship",
    "Pets & Animals",
    "Parenting & Family",
]

FALLBACK_NICHE = "Lifestyle & Vlogs"

_CLASSIFY_TIMEOUT_S = 10


async def classify_niche(raw: str) -> str:
    """Return the canonical niche that best matches the creator's own wording.

    Never raises and never blocks an analysis: any failure (bad response,
    rate limit, timeout) falls back to FALLBACK_NICHE.
    """
    raw = (raw or "").strip()
    if not raw:
        return FALLBACK_NICHE

    # Exact match (e.g. a suggestion chip or canonical label) needs no API call.
    lowered = raw.lower()
    for canonical in CANONICAL_NICHES:
        if lowered == canonical.lower():
            return canonical

    prompt = (
        "You are a content category classifier.\n"
        "Given a creator's self-described niche, return ONLY the single "
        "best-matching category from this list (return the exact string as a "
        "JSON string, nothing else):\n"
        f"{json.dumps(CANONICAL_NICHES)}\n\n"
        f'Creator\'s niche: "{raw}"'
    )

    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            ),
            timeout=_CLASSIFY_TIMEOUT_S,
        )
        value = json.loads(response.text)
        if isinstance(value, str):
            value = value.strip()
            for canonical in CANONICAL_NICHES:
                if value.lower() == canonical.lower():
                    return canonical
    except Exception:
        pass
    return FALLBACK_NICHE
