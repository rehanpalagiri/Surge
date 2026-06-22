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
# ── Emotional intent ────────────────────────────────────────────────────────────
# The feeling each niche's video must evoke in the viewer. Keyed by canonical niche
# (must stay in sync with CANONICAL_NICHES). A niche with no entry → _GENERIC_EMOTION.
# Drives the EMOTIONAL INTENT prompt block + the emotional_analysis output (Phase 2).
NICHE_EMOTIONS: dict[str, str] = {
    "Fitness": "motivated + capable — the viewer should think 'I could do that' and want to start today",
    "Comedy": "amusement / delight — the viewer should smile or laugh out loud within the first watch and want to rewatch",
    "Food": "craving / appetite — the viewer should feel hungry and want to make or order it",
    "Fashion": "aspiration / desire — the viewer should want the look and feel they could pull it off",
    "Beauty": "aspiration + confidence — the viewer should feel they can look better and want to try the technique",
    "Education": "clarity + the 'aha' — the viewer should feel smarter, like a fog lifted, and want to share it",
    "Gaming": "hype / excitement — the viewer should feel the thrill of the play and want more",
    "Music": "mood / vibe — the viewer should feel the emotion (hyped, moved, nostalgic) the track sets",
    "Dance": "awe + energy — the viewer should feel the rhythm and want to move or learn it",
    "Tech": "curiosity + excitement — the viewer should think the future is cool and want the gadget/tip",
    "Finance": "trust + curiosity — the viewer should feel they're getting a reliable insider edge",
    "Money": "aspiration + urgency — the viewer should feel they could earn more and want to act now",
    "Side Hustles": "possibility + motivation — the viewer should think 'I could actually do this' and want the steps",
    "Crypto": "intrigue + FOMO — the viewer should feel early to something and want to learn more",
    "Business": "ambition + respect — the viewer should feel sharper about building and trust the operator",
    "Health": "reassurance + motivation — the viewer should feel informed and empowered to act",
    "Mental Health": "seen + comforted — the viewer should feel understood, a little lighter, not alone",
    "Yoga": "calm + grounded — the viewer's shoulders should drop and they should want to breathe",
    "Travel": "wanderlust / longing — the viewer should feel they need to go there and save the spot",
    "Lifestyle": "aspiration + warmth — the viewer should want that life and feel cozy/inspired",
    "Motivation": "fired-up / inspired — the viewer should feel a surge of drive and want to act now",
    "Sports": "thrill + awe — the viewer should feel the adrenaline of the moment",
    "Dating": "recognition + intrigue — the viewer should think 'that's so true' and want the advice",
    "Art": "wonder + satisfaction — the viewer should feel mesmerized by the process and the reveal",
    "Pets": "warmth / delight — the viewer should go 'aww', smile, and want to share it",
    "Parenting": "seen + reassured — the viewer should feel understood in the chaos and less alone",
    "Kids": "delight + wholesomeness — the viewer should smile and feel the joy/cuteness",
    "Vegan": "inspiration + appetite — the viewer should feel good about it and crave the food",
    "DIY & Crafts": "satisfaction + 'I could make that' — the viewer should feel the itch to try it",
    "Home Decor": "aspiration + calm — the viewer should want that space and feel inspired to redo theirs",
    "Cleaning": "satisfaction / catharsis — the viewer should feel the oddly-satisfying relief of the before/after",
    "Career": "empowerment + clarity — the viewer should feel more in control of their path and want the tip",
    "Real Estate": "aspiration + intrigue — the viewer should want the property or the knowledge to get one",
    "Outdoors": "awe + freedom — the viewer should feel the call of the wild and want to get outside",
    "True Crime": "intrigue + unease — the viewer should feel the chilling pull to know what happened next",
    "Books": "intrigue + warmth — the viewer should feel the urge to add it to their list",
    "Spirituality": "wonder + reassurance — the viewer should feel a sense of meaning and calm",
    "Movies & TV": "intrigue + 'I have to see this' — the viewer should feel the urge to watch or rewatch",
    "Anime": "hype + emotion — the viewer should feel the fandom thrill and want to watch/discuss",
    "Edits": "awe + emotion — the viewer should feel the rush the edit is engineered to deliver",
    "Cars": "desire + awe — the viewer should feel the want and respect the machine",
    "Photography": "awe + inspiration — the viewer should feel struck by the shot and want to create",
    "Sustainability": "hope + motivation — the viewer should feel it matters and that they can help",
    "College": "recognition + reassurance — the viewer should think 'this is so me' and feel more prepared",
    "Luxury": "aspiration + awe — the viewer should feel the desire and the fantasy",
    "Thrifting": "thrill of the find + satisfaction — the viewer should feel the rush of the deal and the transformation",
    "Hair": "aspiration + confidence — the viewer should want the look and feel they could achieve it",
    "Looksmaxxing": "aspiration + motivation — the viewer should feel they can level up their look and want the steps",
    "ASMR": "relaxation / tingles — the viewer should feel calm, soothed, and drawn into the sensation",
    "News": "informed + 'I need to know more' — the viewer should feel up-to-speed and compelled to react or share",
}

_GENERIC_EMOTION = (
    "a clear, intentional feeling — pull the viewer into the one emotion (curiosity, delight, "
    "desire, awe, or motivation) that best fits what this video is trying to do"
)


def get_emotional_target_block(niche: str, secondary_niche: str = "") -> str:
    """The EMOTIONAL INTENT prompt block. Primary niche's target feeling leads; a real,
    different secondary niche adds its feeling as a secondary goal."""
    primary_emotion = NICHE_EMOTIONS.get(niche, _GENERIC_EMOTION)
    lines = [
        "EMOTIONAL INTENT — what this video must make the viewer FEEL (judge this separately from the 6 craft dimensions):",
        f"Primary goal ({niche}): {primary_emotion}.",
    ]
    if secondary_niche and secondary_niche.strip() and secondary_niche != niche:
        sec_emotion = NICHE_EMOTIONS.get(secondary_niche, _GENERIC_EMOTION)
        lines.append(
            f"Secondary goal ({secondary_niche}): {sec_emotion}. The primary feeling leads; "
            f"the video should ALSO carry this where the {secondary_niche} elements appear."
        )
    lines.append(
        "Assess whether the video actually LANDS the primary feeling, name what makes it land or fall "
        "flat, and give concrete ways to amplify it. Emotional payoff is what makes a video shareable — "
        "a technically clean video that evokes nothing still fails."
    )
    return "\n".join(lines)


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


# ── Promote-only multi-niche merge ──────────────────────────────────────────────
# The PRIMARY niche stays the spine of the whole algorithm (seeds, insight, trend,
# calibration, stored canonical_niche all key on it). The SECONDARY niche can only
# RAISE a dimension's weight, never lower one the primary set — primary wins every
# conflict — and the ≤3-critical invariant is preserved. This reshapes the scorecard
# for real without ever fragmenting the single-niche learning loop.
_TIER_RANK = {"critical": 3, "high": 2, "standard": 1, "low": 0}
_RANK_TIER = {3: "critical", 2: "high", 1: "standard", 0: "low"}


def _profile_tiers(p: NicheProfile) -> dict[str, str]:
    """Map every dimension to its tier name for a profile (default 'standard')."""
    tiers = {d: "standard" for d in _ALL_DIMS}
    for d in p.critical:
        tiers[d] = "critical"
    for d in p.high:
        tiers[d] = "high"
    for d in p.low:
        tiers[d] = "low"
    return tiers


def _merge_promote(primary: NicheProfile, secondary: NicheProfile) -> tuple[NicheProfile, list[str]]:
    """Promote-only merge. Returns (merged_profile, promoted_dims) — the dims the secondary
    actually elevated, for the BLEND note. Primary's critical dims keep the ≤3 slots; any
    overflow promoted to critical is demoted back to high."""
    pt = _profile_tiers(primary)
    st = _profile_tiers(secondary)
    merged: dict[str, str] = {}
    promoted: list[str] = []
    for d in _ALL_DIMS:
        # A dim the PRIMARY marked LOW is a deliberate "this doesn't matter for my niche"
        # (e.g. ASMR → cut_frequency). The secondary may NOT promote it — that's the direct
        # conflict where primary wins, and it's what prevents an impossible scorecard
        # ("use few cuts AND many cuts"). Secondary only lifts standard-or-higher dims.
        if pt[d] == "low":
            merged[d] = "low"
            continue
        hi = max(_TIER_RANK[pt[d]], _TIER_RANK[st[d]])
        merged[d] = _RANK_TIER[hi]
        if hi > _TIER_RANK[pt[d]]:
            promoted.append(d)

    # Enforce the ≤3-critical cap — the primary's critical dims keep the slots.
    crit = [d for d in _ALL_DIMS if merged[d] == "critical"]
    if len(crit) > 3:
        keep = list(primary.critical)[:3]
        for d in crit:
            if d not in keep:
                merged[d] = "high"
                if d in promoted:
                    promoted.remove(d)  # capped back to high → not a promotion to critical

    # Primary's critical dims lead (the renderer's cap rules read critical[0]/[1]).
    critical = [d for d in primary.critical if merged[d] == "critical"]
    critical += [d for d in _ALL_DIMS if merged[d] == "critical" and d not in critical]
    high = [d for d in _ALL_DIMS if merged[d] == "high"]
    low = [d for d in _ALL_DIMS if merged[d] == "low"]
    merged_profile = NicheProfile(
        critical=critical, high=high, standard=[], low=low, context=primary.context
    )
    return merged_profile, promoted


def get_blend_note(niche: str, secondary_niche: str) -> str:
    """Standalone secondary-niche promotion note for the data-derived (insight) hierarchy
    path, where the merged static profile isn't rendered. Returns '' when there's no usable
    secondary niche."""
    if not secondary_niche or not secondary_niche.strip() or secondary_niche == niche:
        return ""
    secondary = NICHE_PROFILES.get(secondary_niche)
    if secondary is None:
        return ""
    primary = NICHE_PROFILES.get(niche)
    elevate = [d for d in _ALL_DIMS if d in (set(secondary.critical) | set(secondary.high))]
    if primary is not None:
        pt = _profile_tiers(primary)
        st = _profile_tiers(secondary)
        # Only dims the secondary ranks higher AND the primary didn't deliberately mark LOW
        # (primary's deprioritization wins — same conflict rule as the static merge).
        elevate = [d for d in elevate if _TIER_RANK[st[d]] > _TIER_RANK[pt[d]] and pt[d] != "low"]
    if not elevate:
        return ""
    return (
        f"\nBLEND — this video mixes **{niche}** (primary) with **{secondary_niche}**: beyond the "
        f"data-derived weights above, give extra weight to {', '.join(elevate)} (where "
        f"{secondary_niche} content lives or dies) and reward authentic {secondary_niche} execution. "
        f"Where the two niches conflict, {niche} wins."
    )


def get_dimension_hierarchy_block(niche: str, platform: str, secondary_niche: str = "") -> str:
    """Return the niche-specific DIMENSION HIERARCHY block for the Gemini prompt.

    When `secondary_niche` is a real, profiled niche different from the primary, the rubric is
    the promote-only MERGE of the two (primary wins conflicts). Returns the generic hierarchy
    if the primary niche has no custom profile.
    """
    profile = NICHE_PROFILES.get(niche)
    if profile is None:
        return _GENERIC_HIERARCHY

    secondary_profile = (
        NICHE_PROFILES.get(secondary_niche)
        if (secondary_niche and secondary_niche.strip() and secondary_niche != niche)
        else None
    )
    blend_line = ""
    label = niche
    if secondary_profile is not None:
        profile, promoted = _merge_promote(profile, secondary_profile)
        label = f"{niche} + {secondary_niche}"
        if promoted:
            blend_line = (
                f"BLEND: **{niche}** (primary) blended with **{secondary_niche}** — "
                f"{secondary_niche} raises the weight of {', '.join(promoted)}. Reward authentic "
                f"{secondary_niche} execution, but where the two conflict, {niche} wins."
            )
        else:
            blend_line = (
                f"BLEND: **{niche}** (primary) blended with **{secondary_niche}** — they share the "
                f"same dimension priorities here, so reward authentic {secondary_niche} execution "
                f"within {niche}'s standards."
            )

    pname = "TikTok" if platform == "tiktok" else "Instagram Reels"
    lines: list[str] = [
        f"DIMENSION HIERARCHY — NICHE-SPECIFIC ({label} on {pname}):",
        "Apply these weights INSTEAD OF the generic tier hierarchy when computing overall_score.",
    ]
    if blend_line:
        lines += ["", blend_line]
    lines += [
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
        lines.append(f"LOW WEIGHT for {label} (score independently, but minimal effect on overall_score):")
        for d in profile.low:
            lines.append(f"  • {d}")
        lines.append("")

    lines.append(f"Niche context: {profile.context}")
    lines.append("")
    lines.append(f"overall_score rules for {label} (NOT a simple average — apply these exactly):")

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
    lines.append(f"improvement_plan ordering for {label}: prioritize {priority[0]} fixes above all else.")
    if len(priority) > 1:
        rest = ", ".join(priority[1:3])
        lines.append(
            f"If {priority[0]} is already ≥ 6, prioritize {rest} next."
        )
    if profile.low:
        low_str = ", ".join(profile.low)
        lines.append(
            f"Treat {low_str} as low-priority improvements for {label} — "
            "only flag if severely broken (score ≤ 2)."
        )

    return "\n".join(lines)
