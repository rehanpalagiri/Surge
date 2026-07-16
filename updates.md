# Planned Updates Log

Running log of architecture changes discussed but **not yet built**. Nothing in this
file is implemented — it's a tracking doc so decisions made in planning conversations
aren't lost before we get to them. Update statuses as work starts/lands; move a section
to CLAUDE.md/AGENTS.md once it's actually shipped, and delete it from here.

**Status as of 2026-07-16: this is the final planning update before launch.** No further
architecture decisions are queued behind this file — from here, work shifts to launch
prep and bug fixing. Nothing below is a launch blocker; everything here is deliberately
scoped as "revisit after launch, when we're ready to build it."

Status key: `[ ]` not started · `[~]` decision made, not built · `[x]` decided against / superseded

---

## Grading pipeline architecture

- `[~]` **Multi-provider split** — Gemini does video perception only (possibly in a
  higher/"thinking" tier); Claude does the reasoning + produces the six scores.

  - **Claude model: Sonnet 5 (`claude-sonnet-5`) confirmed, over Opus 4.8.** Near-Opus
    quality on this class of task (structured judgment from a provided description,
    not open-ended reasoning) at ~40% of Opus's per-token price — matters because this
    call runs on every graded video, not as an occasional admin task. Build notes:
    Sonnet 5 runs adaptive thinking at `effort: "high"` by default if unset — start at
    `effort: "medium"` instead for latency/cost in this user-facing wait-for-results
    flow, raise only if critique quality suffers. Use `output_config.format`
    (structured outputs) to enforce the same six-score + critique JSON shape
    `_validate_analysis_result` already expects — the Claude equivalent of Gemini's
    `response_mime_type="application/json"`. Sonnet 5 has an introductory rate
    ($2/$10 per M tokens) through 2026-08-31, reverting to $3/$15 after — don't anchor
    launch cost assumptions to the temporary rate.
  - **Cost estimate:** current all-Flash pipeline runs ~$0.007–0.01/video;
    Gemini-Pro-thinking + Claude Sonnet 5 runs roughly **7–13x that** (~$0.05–0.09/video
    for a 30s clip), driven almost entirely by Gemini Pro's thinking tokens billing at
    the $10/M output rate.
  - **Gemini tier: there's a genuine mid-tier now, not just Flash-vs-Pro.** Google's
    current lineup (per pricing-aggregator sources, not yet verified against
    ai.google.dev directly) is roughly: Flash-Lite (~$0.10/$0.40) → the repo's current
    `gemini-2.5-flash` (~$0.30/$2.50, hardcoded in `telemetry.py`) → Gemini 3 Flash /
    3.5 Flash (~$0.50–$1.50 input, ~$9 output — reportedly matching or beating the Pro
    tier on coding/agentic benchmarks) → Gemini 3.1 Pro (~$2/$12, ≤200k context). Test
    the 3.x Flash tier first for "make Gemini think harder" — meaningfully cheaper than
    Pro on input, only slightly cheaper on output, but if it matches Pro-level
    reasoning on this task, that's most of the quality gain from the Pro-thinking
    estimate above at a smaller cost jump from today's baseline. Also worth testing
    independent of model tier: a thinking budget on whichever Flash model is used,
    without changing tier at all. **Verify exact current pricing at
    ai.google.dev/gemini-api/docs/pricing before locking in a decision** — aggregator
    sites disagree by as much as $0.50/M on some of these numbers.
  - **Why the split, not a swap:** Claude cannot watch video natively (images/PDF only)
    and OpenAI has no native video input either (ffmpeg frame-extraction workaround,
    loses audio/temporal info) — Gemini stays the only real "eyes" option regardless of
    what does the reasoning.

- `[ ]` **Fix 1fps video sampling** — `services/gemini.py`'s perception call never sets
  `video_metadata.fps` or `media_resolution`, so it silently runs at Gemini's 1fps
  default. This under-samples fast cuts and directly undermines `cut_frequency` /
  `hook_velocity` scoring on quick-edit content. Recommended starting point: 2–4fps at
  `media_resolution: "low"` (66 tok/frame vs 258 default) — e.g. 3fps × low-res ≈
  198 tokens/sec, actually *less* than today's 1fps × default-res (258 tokens/sec),
  while tripling temporal sampling. Worth doing regardless of which model tier is used
  for perception.

- `[~]` **Split Gemini's job to summarize/describe only** — no in-pass scoring. Gemini
  produces a rich structured description (section-by-section, timing, emotional read);
  a downstream call (Claude, or a second Gemini call) reasons over that description to
  *produce* the six scores. Endorsed — not a cost saver (roughly cost-neutral to
  slightly more expensive), but fixes a real ordering bug: today's schema emits scores
  *before* their justifying evidence, so evidence can't causally inform the score. This
  restructuring makes it genuine evidence-then-score reasoning instead of after-the-fact
  justification. Revisit when we actually build this — not started.

- `[~]` **Remove `dimension_evidence` as currently structured** — depends on the item
  above landing first. Gets replaced by whatever the new summarize-only pass produces;
  the downstream scorer generates its own evidence-then-score pairs in the correct
  order.

- `[ ]` **Niche auto-detection — decision pending.** User's instinct: remove it (claims
  ~99% self-tested accuracy, seen as a token waste). Counter-point raised: it's bundled
  into the same perception call (not a separate one), so actual token savings are
  small (~250 tokens/video); the real tradeoff is that removing it means every
  un-hinted upload permanently falls back to the generic dimension-priority hierarchy
  instead of a niche-specific one in the advice-writing pass. No final call made yet —
  revisit before touching `_build_perception_prompt`'s STEP 1 in `gemini.py`.

- `[ ]` **Rotating niche-specific rubric criteria — decision pending, leaning against
  a full rotation.** User wants actual different scored criteria per niche (not just
  reweighted priority on the same six). Tradeoff: the current six-dimension scorecard
  is load-bearing everywhere — verdict math (`needed = ceil(4*n/6)`), the frontend's
  fixed six-tile layout, `niche_insights`/`trend_summaries`, and any future
  `craft_correlation.py` cross-niche analysis all assume a consistent shape. Truly
  variable dimensions per niche would fragment all of that (can't compare "Strong
  craft" across niches anymore, historical trends per niche need separate schemas,
  a creator whose niche gets reclassified between uploads loses continuity).
  Recommended middle path if we want niche flavor beyond weighting: keep the six
  universal scored dimensions (verdict/trend/correlation math stays intact), add a
  small **unscored** niche-specific qualitative flag/note (e.g. "ASMR trigger clarity:
  strong") that shows up in critique text only, never feeds the verdict. Full rotating
  rubrics are possible but should be scoped as "verdict math and correlation tooling
  need a redesign," not a drop-in addition.

---

## Seed pool / self-learning loop

- `[~]` **Admin-seed weekly trend synthesis — approved, extend existing infra.**
  `services/seed_insights.py` (`generate_niche_insight`) and
  `services/trend_insights.py` (`generate_trend_insight`) already do "AI reads the
  niche's seed pool and synthesizes patterns" — today it's admin-triggered and only
  shown in the admin dashboard, never fed into live grading. Plan: hook generation onto
  the existing daily scheduler (`services/scheduler.py`) on a weekly cadence, then wire
  the generated block into the live reasoning pass (same pattern as the niche hierarchy
  block already injected today). Smaller lift than new infra — reuses tested code.
  **Model: Claude Opus 4.8, not Gemini.** This step never re-watches video — it
  synthesizes patterns from data already in the DB (stored scores, niche labels,
  verified outcomes), so Gemini's native-video advantage is irrelevant. Runs weekly per
  niche (~50 calls/week), not per-upload, so the cost gap to Sonnet that mattered for
  the per-video scoring call doesn't apply — pay for the best reasoning here.
  **Architecture requirement, not optional: compute the actual statistics in code
  first (extend `tools/craft_correlation.py`'s methodology — Pearson r, Fisher CI,
  sample-size-justified thresholds, naive baselines), then have Opus narrate the
  already-validated numbers into the "what's working in this niche" block.** Do not
  have the LLM freeform "find patterns" over a raw seed dump — that's exactly the
  unvalidated correlation risk CLAUDE.md's correlation/causation rules exist to
  prevent. Not started.

- `[~]` **User-seed self-learning loop ("predicted vs actual") — gated, two-step
  installation. Do not build step 2 before step 1 is done and shows signal.**
  1. **Step 1 (prerequisite):** run `tools/craft_correlation.py` and confirm it shows a
     statistically justified craft↔outcome signal (Pearson r + Fisher CI, sample-size
     justified per CLAUDE.md's thresholds) before any of this touches live scoring —
     matches the existing `SURGE_CALIBRATION_ENABLED` safeguard and its stated reason
     ("risk is runaway self-reinforcement and selection-bias inflation, not accuracy").
  2. **Step 2 (only after step 1 passes):** build the weekly AI summary of "what the
     grader got right/wrong vs. verified outcomes," recency-weighted (this week
     weighted higher than prior weeks' analysis — exact weighting mechanism not yet
     spec'd: formal decay function vs. prompt-only instruction, needs deciding when we
     get here). **Scope: pooled across all users**, not per-creator (explicit choice —
     bigger sample size, but this is the riskier of the two options: a dominant or
     unusual creator's pattern can skew scoring for everyone else, unlike the existing
     per-creator-scoped `craft_insights.py`). Wire the resulting summary into live
     scoring only once step 1's gate is satisfied.
  **Model, once step 1 clears: Claude Opus 4.8**, same reasoning as the admin-seed
  synthesis above — no video re-watching involved, weekly not per-upload call volume,
  and the same "compute the validated statistics in code first, Opus narrates the
  result" principle applies here too.
  Not started — nothing here should touch `services/gemini.py` until Step 1 is done.

---

## Billing & rate limiting

- `[~]` **Rolling 5-hour cost-window limiter — concept and window size confirmed,
  scoped to the paid tier only, not free.** Problem it solves: `is_pro()` is binary and
  Pro means unlimited analyses today, which is fine at current all-Flash cost (~$0.007–
  0.01/video) but stops being fine once the multi-provider pipeline above lands
  (~$0.05–0.09/video) — a single $9.99/mo account uploading heavily could cost more
  than its subscription in a single day. Mechanism: a rolling window (5 hours,
  confirmed) capping spend per account, modeled on Claude.ai/Claude Code. 5 hours holds
  up on reflection — long enough to cover a real editing/testing session (record, tweak
  a hook, re-upload, repeat) without cutting a user off mid-session, short enough that
  even a maximally aggressive user resets several times a day rather than front-loading
  a whole day's cost into one window. A user who maxed every single window all day
  could theoretically approach break-even; normal usage never gets close. Two open
  implementation questions before building:
  - **Rolling-from-first-use vs. fixed clock slots.** Rolling (clock starts on the
    user's first request in a window, resets exactly 5h later — what Claude does) is
    fairer to the user but harder to display ("resets in 3h 42m"). Fixed slots (e.g.
    every 5h on the dot) are simpler UI but can feel arbitrary mid-session. Leaning
    rolling-from-first-use; not fully decided.
  - **Per-window budget size is an unavoidable guess pre-launch** — there's no usage
    data yet. Ship generous rather than tight (loosen-later is a much better user
    experience than tighten-later), and plan to revisit the number itself — not the
    mechanism — once real spend telemetry exists.
  - **Budget it in estimated dollars, not raw tokens.** `usage_events.estimated_cost_micros`
    already exists per call — once Gemini and Claude are both in the pipeline, "tokens"
    stops being a consistent unit between providers (different per-token prices), so a
    token-count cap either over- or under-corrects depending on provider mix. Cost-based
    budgeting stays correct regardless of provider split.
  - **Do not stack this on top of the free tier's existing monthly count.** Free tier's
    "3 analyses/calendar month" is simple and solves a different problem (basic abuse
    prevention on a zero-revenue tier); this rolling-window mechanism is specifically
    for bounding cost exposure on the paid account once "unlimited" gets expensive to
    honor. Two differently-shaped limiters on one tier is confusing UX for no benefit.

- `[x]` **Single price point confirmed — no multi-tier restructure for launch.**
  Three-tier idea (Plus $9.99 / Pro $19.99 / Max $99.99) considered and set aside; the
  rolling-window limiter above is the mechanism doing the actual cost-protection work
  instead. Reasons it was set aside: no felt differentiator between tiers beyond a
  bigger, invisible rolling-window budget that most individual creators would never
  approach; $99.99 implies an agency/team customer needing features (multi-account
  management, bulk upload, team seats) that don't exist today; and three tiers is real
  billing-code scope (multiple Stripe Price IDs, a tier enum replacing the binary
  `is_pro()` flag, per-tier limits, updated webhook mapping), not a pricing-page edit.
  Revisit post-launch once real power-user usage data exists to inform what would
  actually differentiate a second tier.

---

## Provider/cost landscape notes (informational, not action items)

- Gemini remains the only major provider with true native video understanding.
  Claude: images/PDF only, no video content-block type. OpenAI: no native video input,
  official workaround is ffmpeg frame extraction (loses audio + most temporal info).
  Twelve Labs is a real dedicated video-AI platform (Marengo/Pegasus) but positioned for
  structured extraction/search (scenes, on-screen text, faces, transcripts), not
  open-ended qualitative critique-writing — not a fit to replace Gemini's role here.

- Gemini's own lineup now has more than two tiers worth knowing about (Flash-Lite /
  Flash / the newer 3.x Flash tier / Pro) — see the pricing note under "Multi-provider
  split" above. The 3.x Flash tier in particular is worth a real benchmark before
  assuming Pro is required for better video reasoning.

---

## Post-launch

This file is the snapshot at launch. After launch, new architecture ideas go through
the same process (discuss → log here with a status → build when scheduled) rather than
getting decided ad hoc during a bug-fix pass. If an item above starts getting built,
update its status inline rather than opening a second tracking doc.
