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

The multi-provider split, describe-only Gemini pass, and `dimension_evidence` removal
**shipped 2026-07-17** — Gemini describes the video, Claude Sonnet 5 (`effort: "medium"`,
structured outputs) reasons over the description and produces the six scores, so evidence
precedes score; a Claude failure returns an error dict (status=error), never a fabricated
scorecard. See CLAUDE.md/AGENTS.md (`services/gemini.py`, `services/claude_scoring.py`).
What remains open:

- `[ ]` **Gemini perception tier — still open.** The split shipped on `gemini-2.5-flash`
  for the describe-only perception pass. Whether to move that pass to a "thinking"/3.x-Flash
  tier for richer descriptions is unresolved: Gemini 3.5 Flash is $1.50/$9.00 vs 2.5 Flash's
  $0.30/$2.50, and 3.1 Pro $2/$12 (≤200k) — verified at ai.google.dev/gemini-api/docs/pricing
  on 2026-07-17. Benchmark the 3.x Flash tier — or just a thinking budget on 2.5 Flash —
  before assuming a pricier tier is needed for better descriptions.

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

- `[x]` **Single price point confirmed — no multi-tier restructure for launch.**
  Three-tier idea (Plus $9.99 / Pro $19.99 / Max $99.99) considered and set aside; the
  rolling 5-hour cost-window limiter (shipped — see CLAUDE.md/AGENTS.md's
  `services/cost_window.py` entry) is the mechanism doing the actual cost-protection
  work instead. Reasons it was set aside: no felt differentiator between tiers beyond a
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
  Flash / the newer 3.x Flash tier / Pro) — see the "Gemini perception tier" note under
  "Grading pipeline architecture" above. The 3.x Flash tier in particular is worth a real
  benchmark before assuming Pro is required for better video descriptions.

---

## Post-launch

This file is the snapshot at launch. After launch, new architecture ideas go through
the same process (discuss → log here with a status → build when scheduled) rather than
getting decided ad hoc during a bug-fix pass. If an item above starts getting built,
update its status inline rather than opening a second tracking doc.
