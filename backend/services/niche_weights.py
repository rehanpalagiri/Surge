"""Niche-specific dimension weighting profiles for the Gemini scoring prompt.

Each profile defines how the 6 viral dimensions should be weighted when scoring
videos in a specific niche. Different niches have fundamentally different virality
mechanics: Comedy fails if the first 2 seconds aren't funny; ASMR fails if there
are too many cuts; Finance lives on the curiosity gap claim.

Used by gemini.py to inject a niche-specific DIMENSION HIERARCHY block that
replaces the generic tier model (Tier 1/2/3) with niche-aware critical/high/standard/low weights.
"""

from dataclasses import dataclass, field


@dataclass
class NicheProfile:
    critical: list[str]   # ≤ 3 here caps overall_score at 4
    high: list[str]       # strongly shapes overall_score
    standard: list[str]   # normal weight
    low: list[str]        # minimal weight for this niche
    context: str          # why this niche has a different profile


_ALL_DIMS = [
    "hook_velocity",
    "cut_frequency",
    "text_scannability",
    "curiosity_gap",
    "audio_visual_sync",
    "loop_seamlessness",
]

# Keys MUST match CANONICAL_NICHES in niche_classifier.py. Niches without a profile
# fall back to the generic dimension hierarchy.
NICHE_PROFILES: dict[str, NicheProfile] = {

    # ── COMEDY / ENTERTAINMENT ─────────────────────────────────────────────────
    "Comedy": NicheProfile(
        critical=["hook_velocity"],
        high=["cut_frequency", "curiosity_gap"],
        standard=["audio_visual_sync", "loop_seamlessness"],
        low=["text_scannability"],
        context=(
            "Comedy virality is decided entirely in the first 2 seconds — it's either immediately "
            "funny or it gets scrolled. Fast cuts amplify timing and land punchlines. "
            "Text scannability is lowest: comedy is audio-driven and muted viewers miss the "
            "joke regardless of captions."
        ),
    ),

    "Movies & TV": NicheProfile(
        critical=["curiosity_gap"],
        high=["hook_velocity"],
        standard=["cut_frequency", "audio_visual_sync", "loop_seamlessness"],
        low=["text_scannability"],
        context=(
            "Movies & TV content lives on hot takes, rankings, and 'most people missed this' "
            "frames. The curiosity gap (the opening claim or thesis) is the primary driver. "
            "Text scannability is low because this niche is opinion-driven and audio-forward."
        ),
    ),

    "True Crime": NicheProfile(
        critical=["curiosity_gap"],
        high=["hook_velocity", "audio_visual_sync"],
        standard=["cut_frequency", "text_scannability"],
        low=["loop_seamlessness"],
        context=(
            "True crime virality is almost entirely curiosity-gap driven — the unsolved framing, "
            "the chilling detail, the 'this hasn't been reported' hook. The open loop must be set "
            "in the first 5 seconds. Audio-visual sync creates atmospheric tension."
        ),
    ),

    "News": NicheProfile(
        critical=["curiosity_gap"],
        high=["hook_velocity"],
        standard=["cut_frequency", "audio_visual_sync", "text_scannability"],
        low=["loop_seamlessness"],
        context=(
            "News content hooks with urgency and novelty — the claim must feel important and "
            "time-sensitive in the first 2 seconds. Curiosity gap IS the product here. "
            "Loop seamlessness is lowest priority because news content is consumed once."
        ),
    ),

    "Books": NicheProfile(
        critical=["curiosity_gap"],
        high=["hook_velocity"],
        standard=["text_scannability", "cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Book content hooks with a controversial take or life-changing claim about a specific "
            "book. Curiosity gap is primary ('This book changed how I think about money — and most "
            "people miss the point'). Loop seamlessness is lowest priority."
        ),
    ),

    "Spirituality": NicheProfile(
        critical=["curiosity_gap"],
        high=["hook_velocity"],
        standard=["audio_visual_sync", "text_scannability", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "Astrology content hooks with personal relevance ('Your sign is about to experience a "
            "major shift') and curiosity gap. The sign callout or prediction must appear within "
            "3 seconds. Loop seamlessness is lowest priority."
        ),
    ),

    # ── MUSIC / AUDIO ─────────────────────────────────────────────────────────
    "Music": NicheProfile(
        critical=["audio_visual_sync"],
        high=["hook_velocity", "loop_seamlessness"],
        standard=["cut_frequency", "curiosity_gap"],
        low=["text_scannability"],
        context=(
            "Cuts must land on beats — audio-visual sync IS the product in this niche. "
            "Loop seamlessness drives the replay count that signals virality (people rewatch "
            "music content). Text scannability and curiosity gap are least important: "
            "viewers come for the performance, not the reveal."
        ),
    ),

    "ASMR": NicheProfile(
        critical=["audio_visual_sync"],
        high=["loop_seamlessness"],
        standard=["hook_velocity", "text_scannability", "curiosity_gap"],
        low=["cut_frequency"],
        context=(
            "ASMR requires impeccable audio-visual sync (triggers must land exactly on visual cues). "
            "IMPORTANT: a LOW cut_frequency score (2–4) is CORRECT and EXPECTED for this niche — "
            "slow, uninterrupted takes are a feature. Do NOT penalize overall_score for low "
            "cut_frequency. Loop seamlessness drives completion rate. Curiosity gap is minimal."
        ),
    ),

    "Yoga": NicheProfile(
        critical=["audio_visual_sync"],
        high=["loop_seamlessness", "hook_velocity"],
        standard=["curiosity_gap", "text_scannability"],
        low=["cut_frequency"],
        context=(
            "Like ASMR — slow, deliberate visuals matched to ambient audio. "
            "IMPORTANT: a LOW cut_frequency score is EXPECTED and CORRECT for this niche — "
            "frequent cuts destroy the meditative flow. Do NOT penalize overall_score for low "
            "cut_frequency. Loop seamlessness matters because meditation content loops well."
        ),
    ),

    # ── PETS / KIDS ────────────────────────────────────────────────────────────
    "Pets": NicheProfile(
        critical=["hook_velocity"],
        high=["loop_seamlessness", "audio_visual_sync"],
        standard=["cut_frequency", "curiosity_gap"],
        low=["text_scannability"],
        context=(
            "The cute or funny moment must appear in the FIRST 2 seconds — no setup, no intro. "
            "Loop seamlessness drives replays (people rewatch funny animal moments). "
            "Text scannability and curiosity gap are lowest priority: the video IS the hook."
        ),
    ),

    "Kids": NicheProfile(
        critical=["hook_velocity"],
        high=["loop_seamlessness", "audio_visual_sync"],
        standard=["cut_frequency", "curiosity_gap"],
        low=["text_scannability"],
        context=(
            "Baby/kid content must deliver the 'aww' or laugh moment within the first 2 seconds. "
            "Loop seamlessness matters because the best kid content gets replayed many times. "
            "Text scannability is irrelevant — no one is reading while a baby does something funny."
        ),
    ),

    "Parenting": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["audio_visual_sync"],
        standard=["cut_frequency", "loop_seamlessness"],
        low=["text_scannability"],
        context=(
            "Parenting content that opens with a relatable moment or a 'you won't believe what my "
            "kid did' setup hits both hook and curiosity gap simultaneously. The opening must be "
            "instantly relatable to parents. Text scannability is lowest priority since parenting "
            "content is emotionally driven and audio-forward."
        ),
    ),

    # ── FITNESS / HEALTH ───────────────────────────────────────────────────────
    "Fitness": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["cut_frequency", "loop_seamlessness"],
        standard=["audio_visual_sync", "text_scannability"],
        low=[],
        context=(
            "Fitness content needs an immediate visual hook (physique reveal, heavy lift, or "
            "transformation) AND a strong curiosity gap (the 'mistake' or 'secret' framing). "
            "Fast cuts match workout energy. Loop seamlessness is high because workout "
            "montages get rewatched for motivation."
        ),
    ),


    "Health": NicheProfile(
        critical=["curiosity_gap", "hook_velocity"],
        high=["text_scannability"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Health content lives and dies by the curiosity gap — the health claim must create "
            "urgency ('Most people are making this mistake with their sleep'). Text scannability "
            "is high because people screenshot health tips and stats. Loop seamlessness is lowest."
        ),
    ),

    "Mental Health": NicheProfile(
        critical=["curiosity_gap"],
        high=["hook_velocity"],
        standard=["cut_frequency", "text_scannability", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Mental health content hooks through radical vulnerability or a provocative framing "
            "('If you do this every morning, your anxiety is yours to manage'). Curiosity gap "
            "slightly outweighs hook velocity — viewers need to feel 'this is about me' before "
            "committing. Loop seamlessness is lowest priority."
        ),
    ),

    "Sports": NicheProfile(
        critical=["hook_velocity"],
        high=["audio_visual_sync", "cut_frequency"],
        standard=["curiosity_gap", "loop_seamlessness"],
        low=["text_scannability"],
        context=(
            "Sports content hooks with the highlight clip — the impossible shot, the insane play — "
            "and it must appear in the first 2 seconds. Fast cuts and audio-visual sync (crowd "
            "noise, commentary peaks) amplify the energy. Text scannability is least important."
        ),
    ),

    "Outdoors": NicheProfile(
        critical=["hook_velocity"],
        high=["audio_visual_sync"],
        standard=["curiosity_gap", "loop_seamlessness", "cut_frequency"],
        low=["text_scannability"],
        context=(
            "Outdoor content needs a cinematic hook — the most spectacular viewpoint or dramatic "
            "landscape must appear in the first 2 seconds, not after setting up camp. "
            "Audio-visual sync is elevated for ambient nature sounds synced with cuts. "
            "Text scannability matters least in this visual-forward niche."
        ),
    ),

    "Travel": NicheProfile(
        critical=["hook_velocity"],
        high=["audio_visual_sync"],
        standard=["curiosity_gap", "loop_seamlessness", "cut_frequency"],
        low=["text_scannability"],
        context=(
            "Travel content needs the most spectacular location shot in the first 2 seconds, "
            "not the airport or packing sequence. Audio-visual sync is elevated for cinematic "
            "quality (music must match landscape energy). Text scannability is lowest priority."
        ),
    ),

    # ── FOOD / COOKING ─────────────────────────────────────────────────────────
    "Food": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["text_scannability"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "The finished dish or the most visually striking moment must appear in the first "
            "2 seconds. Text scannability is high because viewers screenshot recipes and ingredient "
            "lists. Loop seamlessness matters least — people watch for the recipe, not to rewatch."
        ),
    ),


    "Vegan": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["text_scannability"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Vegan content combines recipe value with ideological hook — curiosity gap "
            "('Is this ACTUALLY better than meat?') drives watch time alongside food reveal hooks. "
            "Text scannability is high for ingredient callouts."
        ),
    ),


    # ── EDUCATION / INFORMATION ────────────────────────────────────────────────
    "Education": NicheProfile(
        critical=["curiosity_gap"],
        high=["text_scannability", "hook_velocity"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Educational content is driven primarily by the curiosity gap — the question or "
            "problem posed must make viewers feel they will lose something by not watching. "
            "Text scannability is high because instructional content needs readable on-screen steps. "
            "Loop seamlessness is lowest — people watch tutorials once."
        ),
    ),

    "Career": NicheProfile(
        critical=["curiosity_gap"],
        high=["text_scannability", "hook_velocity"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Career content virality is almost entirely curiosity-gap driven — 'The one mistake "
            "that got me fired' or 'How I got a $200K offer in 2 months'. The insight must be "
            "teased immediately. Text scannability is high for tip-format lists."
        ),
    ),

    "Finance": NicheProfile(
        critical=["curiosity_gap"],
        high=["text_scannability", "hook_velocity"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Finance content lives entirely on the money claim in the curiosity gap — the claim "
            "must land in the first 3 seconds of the script. Text scannability is high because "
            "finance viewers screenshot data, percentages, and charts. Loop seamlessness is lowest."
        ),
    ),

    "Business": NicheProfile(
        critical=["curiosity_gap"],
        high=["text_scannability", "hook_velocity"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Business content hooks with contrarian insight or income claim. Curiosity gap is "
            "primary. Text scannability is high for metrics, steps, and frameworks. "
            "Loop seamlessness is lowest priority."
        ),
    ),

    "Side Hustles": NicheProfile(
        critical=["curiosity_gap"],
        high=["hook_velocity", "text_scannability"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Side hustle content is pure income-claim curiosity gap ('How I make $3K/month with "
            "my phone'). The income number must appear within 3 seconds. Text scannability is "
            "high for showing actual earnings and steps."
        ),
    ),

    "Real Estate": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["text_scannability"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Real estate content uses the house reveal AND price reveal as dual hooks — the first "
            "frame must show the property, the script must tease the price or deal. Text "
            "scannability is high for price callouts and square footage."
        ),
    ),

    "Crypto": NicheProfile(
        critical=["curiosity_gap"],
        high=["hook_velocity", "text_scannability"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Crypto content is driven by FOMO and curiosity gap — price prediction or 'alpha' "
            "framing. The claim must land in the first 2 seconds. Text scannability is high "
            "for showing charts, percentages, and ticker prices."
        ),
    ),

    "Sustainability": NicheProfile(
        critical=["curiosity_gap", "hook_velocity"],
        high=["text_scannability"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Sustainability content hooks with a surprising environmental claim or challenge. "
            "Curiosity gap and text scannability (stats, numbers) are both elevated. "
            "Loop seamlessness is lowest priority."
        ),
    ),

    # ── FASHION / BEAUTY ───────────────────────────────────────────────────────
    "Fashion": NicheProfile(
        critical=["hook_velocity"],
        high=["curiosity_gap", "text_scannability"],
        standard=["audio_visual_sync", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "Fashion content needs an immediate outfit reveal or fit-check hook. Text scannability "
            "is elevated for brand callouts, prices, and item names — fashion viewers screenshot "
            "these constantly. Curiosity gap frames the reveal ('You'll never guess what this cost')."
        ),
    ),

    "Beauty": NicheProfile(
        critical=["hook_velocity"],
        high=["audio_visual_sync", "text_scannability"],
        standard=["curiosity_gap", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "Beauty content uses the final look or before/after transformation as the immediate "
            "hook. Audio-visual sync is elevated for beat-synced makeup reveal moments. "
            "Text scannability high for product names and prices. Loop seamlessness is lowest."
        ),
    ),


    "Hair": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["text_scannability"],
        standard=["audio_visual_sync", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "Hair content hooks with the transformation reveal and product curiosity gap. "
            "Text scannability is high because product names and steps drive saves — "
            "people screenshot routines. Loop seamlessness is lowest priority."
        ),
    ),

    "Thrifting": NicheProfile(
        critical=["hook_velocity"],
        high=["curiosity_gap", "text_scannability"],
        standard=["audio_visual_sync", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "Street style hooks with an unexpected outfit or price reveal ('This entire fit costs "
            "$40'). Text scannability is elevated for price and brand callouts. The price reveal "
            "IS the curiosity gap and should appear within 5 seconds."
        ),
    ),

    # ── HOME / LIFESTYLE ───────────────────────────────────────────────────────
    "Home Decor": NicheProfile(
        critical=["hook_velocity"],
        high=["audio_visual_sync", "text_scannability"],
        standard=["curiosity_gap", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "Home decor hooks with the room reveal or transformation — the final result must appear "
            "in the first 2 seconds, not after 30 seconds of process. Audio-visual sync is elevated "
            "for cinematic panning shots. Text scannability high for cost and product callouts."
        ),
    ),

    "Cleaning": NicheProfile(
        critical=["hook_velocity"],
        high=["audio_visual_sync"],
        standard=["curiosity_gap", "text_scannability", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "Cleaning content hooks with the satisfying transformation or 'dirty vs clean' "
            "immediate contrast. Audio-visual sync is elevated for satisfying sounds (the squeak "
            "of clean, the vacuum sound). The 'before' state should appear in the first 2 seconds "
            "to set up the payoff."
        ),
    ),

    "DIY & Crafts": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["text_scannability"],
        standard=["audio_visual_sync", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "DIY content hooks with the finished product reveal first, then walks back to the "
            "process. Text scannability is elevated for material lists, step labels, and cost "
            "callouts. The final result must appear immediately."
        ),
    ),

    "Lifestyle": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["loop_seamlessness"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["text_scannability"],
        context=(
            "Vlog content must open with the most compelling moment, not a greeting or intro. "
            "The curiosity gap frames what's about to unfold. Both hook and curiosity gap are "
            "equally critical. Loop seamlessness is elevated for series-style content. "
            "Text scannability is lowest priority."
        ),
    ),


    "Dating": NicheProfile(
        critical=["curiosity_gap"],
        high=["hook_velocity"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness", "text_scannability"],
        context=(
            "Dating content hooks with a relatable frustration or controversial opinion that "
            "creates immediate identification. Curiosity gap is primary. Text scannability and "
            "loop seamlessness are lowest priority."
        ),
    ),

    # ── TECH / GAMING ──────────────────────────────────────────────────────────
    "Gaming": NicheProfile(
        critical=["hook_velocity"],
        high=["audio_visual_sync", "cut_frequency"],
        standard=["curiosity_gap", "loop_seamlessness"],
        low=["text_scannability"],
        context=(
            "Gaming content hooks with the clip — the insane play, the rare drop, the funny "
            "glitch — and it must appear in the FIRST 2 seconds. No intro, no setup. "
            "Audio-visual sync is elevated for commentary peaks and sound effect timing. "
            "Text scannability is lowest priority."
        ),
    ),

    "Tech": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["text_scannability"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Tech content hooks with the product reveal or 'I can't believe this exists' moment "
            "in the first 2 seconds. Text scannability is elevated for price callouts, spec "
            "overlays, and comparison charts — tech viewers screenshot specs."
        ),
    ),

    "Photography": NicheProfile(
        critical=["hook_velocity"],
        high=["audio_visual_sync", "text_scannability"],
        standard=["curiosity_gap", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "Photography content hooks with the before/after edit reveal (must appear immediately). "
            "Audio-visual sync elevated for aesthetic music matches. Text scannability is high "
            "for settings overlays (ISO, shutter speed) and tool names."
        ),
    ),

    # ── CREATIVE ───────────────────────────────────────────────────────────────
    "Art": NicheProfile(
        critical=["hook_velocity"],
        high=["audio_visual_sync", "loop_seamlessness"],
        standard=["curiosity_gap", "cut_frequency", "text_scannability"],
        low=[],
        context=(
            "Art content uses the finished piece or most dramatic moment of the creation process "
            "as the opening hook (timelapse approach). Audio-visual sync elevated for music-matched "
            "reveals. Loop seamlessness works well because creative timelapses reward rewatching."
        ),
    ),

    # ── MOTIVATION / SELF-IMPROVEMENT ──────────────────────────────────────────
    "Motivation": NicheProfile(
        critical=["hook_velocity"],
        high=["curiosity_gap", "audio_visual_sync"],
        standard=["cut_frequency", "loop_seamlessness"],
        low=["text_scannability"],
        context=(
            "Motivation content hooks with a single powerful statement in the first 2 seconds — "
            "the opening line IS the entire hook ('Nobody is coming to save you'). Audio-visual "
            "sync is elevated for music-driven montages. Text scannability is lowest — "
            "motivation is audio-forward and the words are spoken, not captioned."
        ),
    ),

    # ── LUXURY / AUTOMOTIVE ────────────────────────────────────────────────────
    "Luxury": NicheProfile(
        critical=["hook_velocity"],
        high=["text_scannability"],
        standard=["curiosity_gap", "audio_visual_sync", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "Luxury content hooks with the price reveal or the most jaw-dropping visual in the "
            "first 2 seconds — no buildup, just immediate spectacle. Text scannability is "
            "elevated because price, brand, and cost overlays are the entire content strategy. "
            "Loop seamlessness is lowest priority."
        ),
    ),

    "Cars": NicheProfile(
        critical=["hook_velocity"],
        high=["audio_visual_sync"],
        standard=["curiosity_gap", "cut_frequency", "text_scannability"],
        low=["loop_seamlessness"],
        context=(
            "Car content hooks with the most visually impressive moment (the startup sequence, "
            "the drive reveal, the modification) in the first 2 seconds. Audio-visual sync is "
            "elevated because engine sounds are as important as visuals in automotive content."
        ),
    ),

    # ── COMMUNITY / COLLEGE ────────────────────────────────────────────────────
    "College": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["audio_visual_sync"],
        standard=["cut_frequency", "loop_seamlessness"],
        low=["text_scannability"],
        context=(
            "College content hooks with a highly relatable shared experience or an 'only at "
            "[university]' moment that creates instant identification. Both hook velocity and "
            "curiosity gap are equally important. Text scannability is lowest priority."
        ),
    ),

    # ── NEW (2026-06): Money / Dance / Looksmaxxing / Edits / Anime ─────────────
    "Money": NicheProfile(
        critical=["curiosity_gap"],
        high=["hook_velocity", "text_scannability"],
        standard=["cut_frequency", "audio_visual_sync"],
        low=["loop_seamlessness"],
        context=(
            "Money content is pure curiosity-gap — the savings claim, the 'nobody tells you this' "
            "money hack, or the income/net-worth reveal must land in the first 3 seconds. Text "
            "scannability is high because viewers screenshot dollar figures, percentages, and "
            "step lists. Loop seamlessness is lowest priority."
        ),
    ),

    "Dance": NicheProfile(
        critical=["audio_visual_sync"],
        high=["hook_velocity", "loop_seamlessness"],
        standard=["cut_frequency", "curiosity_gap"],
        low=["text_scannability"],
        context=(
            "Dance virality lives on audio-visual sync — the moves must hit exactly on the beat. "
            "The first move has to land in the opening second (no walk-up, no intro). Loop "
            "seamlessness drives the rewatches and duets that signal virality. Text scannability "
            "is least important — viewers come for the performance."
        ),
    ),

    "Looksmaxxing": NicheProfile(
        critical=["hook_velocity", "curiosity_gap"],
        high=["text_scannability"],
        standard=["audio_visual_sync", "cut_frequency"],
        low=["loop_seamlessness"],
        context=(
            "Looksmaxxing content hooks with a before/after transformation reveal and a 'how-to' "
            "curiosity gap (the routine, tip, or product that drove the glow-up). The reveal or "
            "rating must appear immediately. Text scannability is elevated for step lists, product "
            "names, and rating overlays viewers screenshot."
        ),
    ),

    "Edits": NicheProfile(
        critical=["audio_visual_sync", "hook_velocity"],
        high=["loop_seamlessness", "cut_frequency"],
        standard=["curiosity_gap"],
        low=["text_scannability"],
        context=(
            "Edits live and die on audio-visual sync — every cut, zoom, and transition must hit "
            "the beat or the drop. The most striking frame has to open the video (no build-up). "
            "Cut frequency and loop seamlessness drive the rewatches that make edits go viral. "
            "Text scannability is least important — edits are felt, not read."
        ),
    ),

    "Anime": NicheProfile(
        critical=["hook_velocity"],
        high=["curiosity_gap", "audio_visual_sync"],
        standard=["cut_frequency", "loop_seamlessness"],
        low=["text_scannability"],
        context=(
            "Anime content hooks with the clip — the iconic moment, the power-up, the plot twist — "
            "and it must hit in the first 2 seconds. Curiosity gap drives takes, rankings, and "
            "'if you know, you know' framing; audio-visual sync matters because anime edits and "
            "scenes are scored to music. Text scannability is lowest priority."
        ),
    ),
}


# Generic fallback — returned when the niche has no profile defined
_GENERIC_HIERARCHY = (
    "DIMENSION HIERARCHY — used for overall_score, verdict, and predictions:\n"
    "Tier 1 — GATING (determines if anyone watches past 3 seconds): hook_velocity, curiosity_gap\n"
    "Tier 2 — RETENTION (determines if viewers complete the video): cut_frequency, audio_visual_sync\n"
    "Tier 3 — AMPLIFICATION (multiplies reach once Tier 1/2 are strong): text_scannability, loop_seamlessness\n"
    "\n"
    "overall_score computation rules (NOT a simple average — apply these exactly):\n"
    "- If BOTH hook_velocity AND curiosity_gap are ≤ 3 → overall_score is capped at 4.\n"
    "- If EITHER hook_velocity OR curiosity_gap is ≤ 3 → overall_score is capped at 5.\n"
    "- Otherwise: overall_score is a holistic judgment weighted toward Tier 1, then Tier 2, then Tier 3.\n"
    "- A video with hook=8, curiosity=8, everything else=5 → overall can reach 7.\n"
    "- A video with hook=3, curiosity=3, everything else=9 → overall cannot exceed 4.\n"
    "\n"
    "improvement_plan ordering: Tier 1 fixes (hook_velocity, curiosity_gap) almost always "
    "outrank Tier 2 fixes, which outrank Tier 3 — UNLESS the Tier 1 dimensions are already "
    "strong (≥ 6)."
)


def get_dimension_hierarchy_block(niche: str, platform: str) -> str:
    """Return the niche-specific DIMENSION HIERARCHY block for the Gemini prompt.

    Returns the generic hierarchy if the niche has no custom profile.
    """
    profile = NICHE_PROFILES.get(niche)
    if profile is None:
        return _GENERIC_HIERARCHY

    pname = "TikTok" if platform == "tiktok" else "Instagram Reels"
    lines: list[str] = [
        f"DIMENSION HIERARCHY — NICHE-SPECIFIC ({niche} on {pname}):",
        "Apply these weights INSTEAD OF the generic tier hierarchy when computing overall_score.",
        "",
        "CRITICAL — a score of ≤ 3 here caps overall_score at 4:",
    ]
    for d in profile.critical:
        lines.append(f"  • {d}")
    lines.append("")
    lines.append("HIGH WEIGHT — strongly shapes overall_score:")
    for d in profile.high:
        lines.append(f"  • {d}")
    lines.append("")

    # Standard — any dim not already in critical or high or low
    accounted = set(profile.critical) | set(profile.high) | set(profile.low)
    std = [d for d in _ALL_DIMS if d not in accounted]
    if std:
        lines.append("STANDARD WEIGHT:")
        for d in std:
            lines.append(f"  • {d}")
        lines.append("")

    if profile.low:
        lines.append(f"LOW WEIGHT for {niche} (score independently, but minimal effect on overall_score):")
        for d in profile.low:
            lines.append(f"  • {d}")
        lines.append("")

    lines.append(f"Niche context: {profile.context}")
    lines.append("")
    lines.append(f"overall_score rules for {niche} (NOT a simple average — apply these exactly):")

    if len(profile.critical) == 1:
        g = profile.critical[0]
        lines.append(f"- If {g} ≤ 3 → overall_score is capped at 4 (non-negotiable for this niche).")
        lines.append(
            f"- Otherwise: weight {g} and the HIGH dimensions above most heavily. "
            f"LOW dimensions have minimal influence — a video can reach overall_score 8 "
            f"even with LOW dimensions at 2–3, as long as CRITICAL and HIGH are strong."
        )
    else:
        g0, g1 = profile.critical[0], profile.critical[1]
        lines.append(f"- If BOTH {g0} AND {g1} ≤ 3 → overall_score is capped at 4.")
        lines.append(f"- If EITHER {g0} OR {g1} ≤ 3 → overall_score is capped at 5.")
        lines.append(
            "- Otherwise: weight CRITICAL and HIGH dimensions most heavily. "
            "LOW dimensions have minimal influence on the final holistic score."
        )

    lines.append("")
    priority = profile.critical + [d for d in profile.high if d not in profile.critical]
    lines.append(f"improvement_plan ordering for {niche}: prioritize {priority[0]} fixes above all else.")
    if len(priority) > 1:
        rest = ", ".join(priority[1:3])
        lines.append(
            f"If {priority[0]} is already ≥ 6, prioritize {rest} next."
        )
    if profile.low:
        low_str = ", ".join(profile.low)
        lines.append(
            f"Treat {low_str} as low-priority improvements for {niche} — "
            "only flag if severely broken (score ≤ 2)."
        )

    return "\n".join(lines)
