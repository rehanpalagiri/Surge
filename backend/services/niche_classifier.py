"""Maps a creator's free-text niche description to one of the canonical
niches used for seed matching. The canonical label keeps seed bucketing
deterministic; the raw text still goes to the analysis prompt for specificity.

Honesty layer (#4, on top of #6): a niche Surge isn't sure about routes to the
``Uncategorized`` sentinel — which matches no NicheInsight / seed / TrendSummary,
so grading falls back to the generic dimension hierarchy (neutral weights) — and
flags ``needs_confirmation`` instead of silently scoring as the wrong niche.
"""
import re
import asyncio
import json

from google.genai import types

from services.gemini import client

CANONICAL_NICHES = [
    # Original 20
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
    # Extended 30
    "Skincare & Glow",
    "Weight Loss Journey",
    "Yoga & Meditation",
    "Baking & Desserts",
    "Vegan & Plant-Based",
    "DIY & Crafts",
    "Home Decor & Interior",
    "Cleaning & Organization",
    "Career & Job Tips",
    "Real Estate",
    "Side Hustles",
    "Crypto & Web3",
    "Outdoor & Hiking",
    "True Crime & Mystery",
    "Books & Reading",
    "Astrology & Spirituality",
    "Movies & TV",
    "Cars & Automotive",
    "Photography & Editing",
    "Sustainability & Eco",
    "Mental Health",
    "Cooking on a Budget",
    "Couples & Romance",
    "College & Student Life",
    "Luxury & Wealth",
    "Street Style & Thrift",
    "Hair Care & Styling",
    "Kids & Baby",
    "ASMR & Relaxation",
    "News & Commentary",
]

# Sentinel — deliberately NOT in CANONICAL_NICHES. An "Uncategorized" niche
# matches no NicheInsight / seed / TrendSummary lookup, so grading falls back to
# the generic dimension hierarchy: unknown niche → neutral weights, never the
# wrong niche's weights. Analysis still completes.
UNCATEGORIZED = "Uncategorized"

_CLASSIFY_TIMEOUT_S = 10


def _match_canonical(value: str) -> str | None:
    """Resolve free text to a canonical niche, or None if nothing fits (#6).

    Exact (case-insensitive) match first, then a near-miss: the text equals one
    side of an ``&``/``/``-joined canonical label — so "Finance" → "Finance &
    Investing" and "Makeup" → "Beauty & Makeup". ``""``/``"NONE"`` → None.
    """
    v = (value or "").strip().lower()
    if not v or v == "none":
        return None
    # Exact (case-insensitive).
    for c in CANONICAL_NICHES:
        if v == c.lower():
            return c
    # Near-miss: the text equals a segment of a compound canonical label.
    for c in CANONICAL_NICHES:
        for seg in re.split(r"[&/,]", c.lower()):
            if v == seg.strip():
                return c
    return None


async def classify_niche(raw: str) -> dict:
    """Map free text → {canonical (primary), secondary, confidence, needs_confirmation}.

    Never raises, never blocks. Unknown/off-list/failure → UNCATEGORIZED +
    needs_confirmation, NEVER a silent real niche. Secondary is advisory only (#6).
    """
    raw = (raw or "").strip()
    if not raw:
        return {"canonical": UNCATEGORIZED, "secondary": None,
                "confidence": "low", "needs_confirmation": True}

    exact = _match_canonical(raw)
    if exact and exact.lower() == raw.lower():            # explicit chip pick
        return {"canonical": exact, "secondary": None,
                "confidence": "high", "needs_confirmation": False}

    prompt = (
        "You are a content category classifier. From the list, choose the PRIMARY category that "
        "best fits, and a SECONDARY only if the video genuinely blends two niches. "
        'If NO category genuinely fits the primary, return "NONE" for primary — do not force a weak match. '
        "Also rate your confidence in the primary.\n\n"
        f"Categories: {json.dumps(CANONICAL_NICHES)}\n\n"
        f'Creator\'s niche: "{raw}"\n\n'
        'Return ONLY: {"primary": "<exact category or NONE>", '
        '"secondary": "<exact category or NONE>", "confidence": "high" | "low"}'
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
        data = json.loads(response.text)
        if isinstance(data, dict):
            primary = _match_canonical(str(data.get("primary", "")))
            secondary = _match_canonical(str(data.get("secondary", "")))
            conf = "low" if str(data.get("confidence", "")).lower() == "low" else "high"
            if primary:                                   # confident enough to route
                if secondary == primary:
                    secondary = None
                return {"canonical": primary, "secondary": secondary,
                        "confidence": conf, "needs_confirmation": conf == "low"}
    except Exception:
        pass

    # No confident primary (NONE / no-match / failure) → Uncategorized + confirm.
    # NOT a silent real niche — that would poison the wrong rubric.
    return {"canonical": UNCATEGORIZED, "secondary": None,
            "confidence": "low", "needs_confirmation": True}
