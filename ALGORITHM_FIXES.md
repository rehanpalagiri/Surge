# Algorithm Fixes — Master Work Orders

Each section below is a **self-contained prompt**. Copy one section into a fresh Claude Code
session (or hand it to a subagent) and it has everything needed to do the job: exact file, the
current code to locate, the change, the reason, the project constraints, and how to verify.

They are ordered by confidence/leverage. **1–3 are the concrete code fixes I'd do first.**
Locate edits by the quoted snippet, not the line number (numbers drift).

**Shared constraints that apply to EVERY prompt below** (from `CLAUDE.md` / `AGENTS.md`):
- Do **not** deploy, push, or trigger Railway. Do not commit unless asked.
- Backend gate before finishing: `cd backend && source venv/bin/activate && PYTHONPATH=. python -m unittest discover -s tests` and `python -m compileall -q .`
- Preserve unrelated local changes (there is an in-progress edit to `frontend/app/sample/page.tsx`).
- The outcome metric is the **observed like rate** only — never relabel it quality/retention/reach, and never turn it into a forecast.
- Any minimum sample size or threshold needs a **stated statistical justification** — no invented round numbers.
- Keep AI craft assessment separate from observed platform outcomes.

---

## PROMPT 1 — Fix the degenerate median split in craft insights (HIGH confidence, real defect)

**File:** `backend/services/craft_insights.py`
**Function:** `build_craft_insights`, inside the per-dimension pattern loop.

**Problem.** `PATTERN_MIN = 6` and its own comment (plus `CLAUDE.md`) justify the threshold as
"a non-degenerate median split needs **≥3 per side**." But the split guard only enforces one per
side. Because craft scores are discrete and cluster (mostly 5–8), a median tie routinely yields
lopsided splits like 5-vs-1 — and then ONE post's like rate becomes an entire "pattern" shown to
the creator as signal. The code does not honor the documented contract.

**Locate this exact code:**
```python
            mh, ml = _median(high), _median(low)
```
and just above it:
```python
            high = [p["like_rate"] for p in scored if p["scores"][dim] >= dim_median]
            low = [p["like_rate"] for p in scored if p["scores"][dim] < dim_median]
            # Need both sides populated to compare at all.
            if len(high) < 1 or len(low) < 1:
                continue
```

**Change.** Replace the guard so each side needs at least 3 observations, matching the stated
justification:
```python
            # A median split is only non-degenerate when EACH half holds >= 3
            # observations (CLAUDE.md: "a non-degenerate median split needs >=3 per
            # side"). Discrete, tie-heavy scores otherwise yield lopsided splits like
            # 5-vs-1 where one post's like rate defines a whole "pattern".
            _SPLIT_MIN_PER_SIDE = 3
            if len(high) < _SPLIT_MIN_PER_SIDE or len(low) < _SPLIT_MIN_PER_SIDE:
                continue
```
(Define `_SPLIT_MIN_PER_SIDE = 3` as a module constant near `PATTERN_MIN` instead of inline if you
prefer — either is fine, just keep the justification comment.)

**Acceptance criteria.**
- A dimension whose median split is 5-vs-1 (or any split with a side < 3) no longer emits a pattern.
- `PATTERN_MIN = 6` still gates loop entry and the per-dimension scored subset; this is an
  ADDITIONAL guard on the realized split, not a replacement.
- Add/extend a test in `backend/tests/test_craft_insights.py`: construct 6 posts where one
  dimension's scores force a 5-vs-1 median split and assert that dimension is absent from
  `patterns`, while a cleanly-splittable dimension still appears.

---

## PROMPT 2 — Add a minimum-views floor before computing an observed like rate (HIGH confidence)

**Files:** `backend/services/craft_insights.py` AND `backend/tools/craft_correlation.py`
(both compute `likes / views` with only a `views > 0` guard — fix both, identically).

**Problem.** `like_rate = 100 * likes / views` is a binomial proportion estimate. At low view
counts it is almost pure noise: a post with 3 views and 1 like enters the stats as a 33% like rate
and can dominate a 6-post median. Right now the only guard is `views > 0`.

**Statistical justification (use this, do not invent a round number without reasoning).**
The observed rate's resolution is one like `= 1/views`. Requiring `1/views <= 0.01` means a single
like moves the observed rate by at most 1 percentage point, so a rate is never *defined* by one
like. That gives a floor of **views >= 100**. (If you want a tighter floor tied to standard error:
at an assumed like rate p=0.05 the binomial SE is `sqrt(p(1-p)/views)`; SE <= 1pp needs
views >= ~475. Pick 100 as the resolution floor or ~475 as the SE floor, but STATE which and why
in the constant's comment. Do not ship a bare number.)

**In `backend/services/craft_insights.py`:**
- Add near the other constants:
```python
# A like rate on very few views is noise: its resolution is one like = 1/views.
# Requiring 1/views <= 0.01 (a single like moves the observed rate by <= 1 point)
# floors this at 100 views. Below it we do not treat likes/views as an observed rate.
MIN_VIEWS_FOR_RATE = 100
```
- Locate the latest-snapshot filter:
```python
    for s in snaps:
        if not s.views or s.views <= 0 or s.likes is None:
            continue
```
and change the condition to `if not s.views or s.views < MIN_VIEWS_FOR_RATE or s.likes is None:`.

**In `backend/tools/craft_correlation.py`:**
- Import the constant from craft_insights (it already imports several symbols from there):
```python
from services.craft_insights import (
    DIMENSIONS, DIMENSION_LABELS, HORIZON_ORDER, VERIFIED_SOURCES, _craft_scores,
    MIN_VIEWS_FOR_RATE,
)
```
- Apply the same `s.views < MIN_VIEWS_FOR_RATE` guard in its `for s in snaps:` latest-snapshot loop.

**Honest tradeoff to preserve.** A creator whose only verified posts are all below the floor will
see fewer/zero posts in insights. That is correct — we are not inventing a rate we cannot support.
The "preliminary" (n>=1) path in craft_insights still applies to posts that DO clear the floor.

**Do NOT** switch to Beta/Wilson-smoothed rates here — that would stop being an *observed* rate,
which `CLAUDE.md` forbids relabeling. A hard floor keeps the metric honestly "observed."

**Acceptance criteria.**
- Posts with `views < MIN_VIEWS_FOR_RATE` never contribute to `posts`, `patterns`, `observed_range`,
  or the correlation report.
- Add a test asserting a 3-view/1-like snapshot is excluded and does not appear as a 33% like rate.
- Full backend test suite still passes.

---

## PROMPT 3 — Add Spearman rank correlation alongside Pearson in the validation tool (MEDIUM-HIGH)

**File:** `backend/tools/craft_correlation.py`

**Problem.** Pearson r is fragile for this data: like rates are skewed and bounded, craft scores
are compressed into a narrow band (restricted range attenuates r), and n stays small for a long
time — so a single outlier can swing the coefficient. Spearman (rank correlation) is far more
robust to exactly those conditions and is a better default signal for whether a dimension tracks
outcomes. Report BOTH so they can be compared.

**Add a Spearman helper** near `pearson_r`:
```python
def _rankdata(values: list[float]) -> list[float]:
    """Fractional ranks with ties averaged (competition-style average ranks)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-based average rank for the tie group
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_r(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation = Pearson on ranks; None when undefined."""
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    return pearson_r(_rankdata(xs), _rankdata(ys))
```

**Wire it into the per-dimension block.** Where each dimension dict is built with `"r"` and
`"ci95"`, also compute and include Spearman:
```python
        r = pearson_r(xs, ys)
        rho = spearman_r(xs, ys)
        dimensions.append({
            "dimension": dim,
            "label": DIMENSION_LABELS[dim],
            "n": len(paired),
            "r": round(r, 3) if r is not None else None,
            "ci95": _round_pair(fisher_ci(r, len(paired))),
            "spearman": round(rho, 3) if rho is not None else None,
            "insufficient": len(paired) < min_n,
        })
```
Do the same for the baselines block if you want parity (optional but nice).

**Update the text report** in `_print_report` so the per-dimension line prints Spearman next to
Pearson, e.g. add a `rho` column. Keep the existing `--json` output backward-compatible (new key
is additive).

**Acceptance criteria.**
- `python -m tools.craft_correlation --json` includes a `spearman` field per dimension.
- `_rankdata([3,1,2,2])` returns `[4.0, 1.0, 2.5, 2.5]` (ties averaged) — add a unit test for this
  in `backend/tests/test_craft_correlation.py`.
- Existing correlation tests still pass.

---

## PROMPT 4 — Build an offline score-distribution histogram tool (MEDIUM, diagnostic)

**New file:** `backend/tools/score_distribution.py` (read-only, offline, NEVER in the request path
— same class of tool as `tools/craft_correlation.py`).

**Why.** LLM graders notoriously collapse to a narrow 5–7 band. If they do, the verdict thresholds
(`>=7` strong, `>=5` workable in `services/gemini.py::_validate_analysis_result`) are effectively
arbitrary and the rubric isn't discriminating. Every score is already stored in
`UserAnalysis.scores_json` — we just need to look. This tells you whether the prompt anchors need
work BEFORE spending effort anywhere else.

**Spec.**
- Load all `UserAnalysis` rows with `status == "complete"` and a parseable `scores_json`
  (reuse `services.craft_insights._craft_scores` to extract the six dimensions; it already returns
  `None` for not-applicable dimensions — exclude those from that dimension's histogram).
- For each of the six dimensions print: n, mean, median, stdev, and an integer-bucket histogram
  (0..10) with a simple text bar. Also print the share of scores in the 5–7 band per dimension.
- Add a combined line flagging any dimension where >= 80% of scores fall in 5–7 (a compression
  warning), with a note that this is diagnostic, not a pass/fail.
- Mirror the CLI shape of `craft_correlation.py`: `argparse`, `--json` flag, an async `_amain` that
  opens `AsyncSessionLocal()`, and a `main()` entry point. Reuse `DIMENSIONS`/`DIMENSION_LABELS`
  from `services.craft_insights`.
- Header comment must state: read-only, offline, not in the request path, and that it measures the
  grader's own score spread — NOT outcomes and NOT accuracy.

**Acceptance criteria.**
- `cd backend && PYTHONPATH=. python -m tools.score_distribution` runs and prints per-dimension
  histograms (empty-DB case prints a clean "no completed analyses" message, doesn't crash).
- `--json` emits a machine-readable version.
- Add it to the "Offline analysis tools" list in `CLAUDE.md` and `AGENTS.md`.

---

## PROMPT 5 — Pin/record the served Gemini model version so score drift is visible (MEDIUM)

**File:** `backend/services/gemini.py` (plus a schema shim — read carefully).

**Problem.** Both passes call `model="gemini-2.5-flash"`, a MOVING alias. `temperature=0` + seed pin
the sampling, but Google can swap the underlying weights behind the alias and silently shift the
whole score distribution with the seed unchanged. Today that drift would be invisible.

**Preferred: record the served model version** (keeps flexibility, makes drift a visible step-change).
The google-genai response commonly exposes `response.model_version`. Capture it and store it on the
usage event.

1. In `backend/services/telemetry.py`, add an optional `model_version: str | None = None` parameter
   to `record_usage_event` and pass it into the `UsageEvent(...)` construction.
2. Add a `model_version` column to the `UsageEvent` model in `backend/models.py` (nullable string).
   Because this is an existing-table column addition, per `CLAUDE.md` you MUST also add the additive
   shim in `backend/main.py` `_ensure_columns` for BOTH SQLite and Postgres (follow the pattern
   already there for other added columns). `create_all` covers fresh DBs; the shim covers existing.
3. In `analyze_video`'s perception and reasoning `record_usage_event(...)` calls, pass
   `model_version=getattr(perception_resp, "model_version", None)` (and the reasoning response
   respectively). Use `getattr` with a default so a missing attribute never breaks the call.

**Alternative/simpler (if you'd rather not touch the schema): pin a dated model id.** Replace the
alias `"gemini-2.5-flash"` with a specific dated snapshot id in the two `analyze_video` generate
calls AND the constant the stability test asserts against. Downside: you must bump it deliberately
when Google retires the snapshot. If you choose this, verify the exact available snapshot id first
(don't guess a date) and update `tests/test_score_stability.py` accordingly.

**Recommendation:** do the record-version approach; it's non-breaking and turns a silent drift into
an observable one in `usage_events`. Only pin the id if you want hard reproducibility guarantees.

**Acceptance criteria.**
- A completed analysis writes the served model version onto its usage events (or the model id is
  pinned and the stability test updated).
- Backend tests + `compileall` pass. If you added the column, confirm the `_ensure_columns` shim is
  present for both engines.
- **Batch this with any other pending backend change** — per `CLAUDE.md` deploy discipline, don't
  spend a backend deploy on this alone. (You are NOT deploying now; just don't leave it as a
  one-off push later.)

---

## PROMPT 6 — Distinguish "emotion not assessed" from a real 0/10 (LOW-MEDIUM, two files)

**Files:** `backend/services/gemini.py` and the results UI that renders `emotional_analysis`
(`frontend/app/results/[id]/page.tsx` — grep for `achieved_score` / `emotional_analysis`).

**Problem.** In `_validate_analysis_result`, a missing/malformed `achieved_score` is coerced to `0`:
```python
    score = emotional.get("achieved_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        score = 0
    else:
        score = max(0, min(10, int(round(score))))
```
So "the model didn't return a score" renders identically to "this video evokes nothing (0/10)" —
a real but rare misattribution (the perception pass almost always returns it).

**Change (backend).** Represent not-assessed distinctly. Minimal approach: keep `achieved_score`
numeric for the valid case but add a sibling boolean the UI can read:
```python
    raw_score = emotional.get("achieved_score")
    assessed = not (isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)) or not math.isfinite(raw_score))
    score = max(0, min(10, int(round(raw_score)))) if assessed else None
    ...
    result["emotional_analysis"] = {
        "target_emotions": targets,
        "achieved_score": score,          # None when not assessed
        "assessed": assessed,
        "what_lands": str(emotional.get("what_lands") or ""),
        "what_misses": str(emotional.get("what_misses") or ""),
        "how_to_amplify": amplify,
    }
```

**Change (frontend).** Where the emotional block renders `achieved_score/10` and a bar width,
handle `achieved_score == null` / `assessed === false` by showing "Not assessed" instead of "0/10"
and rendering no NaN-width bar. Verify in BOTH light and dark themes (see `UX.md`).

**Caution.** `achieved_score` going from always-numeric to nullable is a contract change — check
every frontend read of it (and `lib/api.ts` typings) so nothing does math on `null`. If the coupling
is wider than expected, keep `achieved_score` as-is and gate purely on a new `assessed` flag instead.

**Acceptance criteria.**
- A malformed/missing emotional score renders "Not assessed", not "0/10".
- A genuine 0 still renders "0/10".
- Backend tests pass; frontend `npx tsc --noEmit` passes.

---

## PROMPT 7 — Fix stale documentation about what gets injected into the live grader (LOW, docs-only)

**Files:** `CLAUDE.md` and `AGENTS.md` (keep them synchronized — they mirror each other).

**Problem.** The docs describe `services/gemini.py` as one that "injects niche/trend/channel
intelligence." In the current code the LIVE review is deliberately outcome-blind: `routers/analyze.py`
hard-sets `effective_mode = "craft_review"` and only the **dimension hierarchy** and
**emotional-target** blocks (from `services/niche_weights.py`) are injected into the reasoning prompt.
Trend/seed/channel intelligence is NOT in the live path. The docs overstate what the grader sees.

**Change.** In the `services/gemini.py` bullet under "Key services and routes", replace
"injects niche/trend/channel intelligence" with an accurate description, e.g.: "injects the
niche-specific dimension-priority hierarchy and the niche emotional-target hint (from
`niche_weights.py`) into the text reasoning pass only; the live review is otherwise blind to prior
outcomes, seed labels, trend summaries, and channel history." Make the SAME edit in both files.

**Acceptance criteria.**
- Both files describe the live injection accurately and remain mirror-identical.
- No code changes.

---

## NOT A CODE FIX — the thing that actually determines if the algorithm is "good"

**Validity is unmeasured, and no prompt above changes that.** `temperature=0` buys reproducibility,
not correctness. Until `tools/craft_correlation.py` has **n >= 8 verified, age-matched posts at a
fixed maturity window** AND the craft dimensions beat the naive baselines (caption length, posting
hour) already built into that report, whether the scores mean anything is unknown.

The highest-leverage work is unglamorous: get verified outcomes flowing (drive post-linking /
provider fetches so `outcome_snapshots` accumulates), then run:
```bash
cd backend && PYTHONPATH=. python -m tools.craft_correlation --horizon 7d
```
Treat the dimensions as validated only for windows where n clears `min_n` and the CI excludes the
baseline. Prompts 1–4 make that measurement trustworthy; they do not substitute for it.

**Lower-priority note (not scheduled above):** `services/trend_insights.py` labels Gemini-rated
seeds (`rating >= 6`) as "HIGH PERFORMERS", conflating the AI's own opinion with market outcomes.
It's currently off the live path, so it's harmless today — but fix that framing before that system
is ever revived.
