# Blueprint — Three-Mode Analysis Engine

Reference document for the Quick / Thinking / Deep Thinking upgrade.
Every section is the **locked** design. Build in the order in §11.

---

## 0. Prerequisites you (the operator) own

- [ ] Confirm the original curated seed video files exist locally (needed to re-populate the library — the pipeline deletes them server-side after analysis).
- [ ] Run the Neon migration SQL (§1) **before** deploying new code.
- [ ] Run the seed wipe (§11 step 10) **after** deploying new code.
- [ ] Re-upload seeds while the backend is warm (sync Gemini call on a single worker).

---

## 1. Schema migration (run on Neon FIRST, app stays up)

Adding columns is backward-compatible — old code ignores them. `performed` is
relaxed, not dropped (drop is irreversible and buys nothing).

```sql
ALTER TABLE seed_videos   ADD COLUMN IF NOT EXISTS rating INTEGER;
ALTER TABLE seed_videos   ADD COLUMN IF NOT EXISTS gemini_analysis TEXT;
ALTER TABLE seed_videos   ALTER COLUMN performed DROP NOT NULL;
ALTER TABLE user_analyses ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'quick';
```

Local SQLite dev: delete `viraliq.db` and let `create_all` rebuild from the model
(throwaway data), or add the same columns to `_ensure_columns` in `main.py`.

---

## 2. Data model changes

### `seed_videos`
| field | change | notes |
|---|---|---|
| `rating` | **ADD** `INTEGER` | 0–10 virality, extracted from `gemini_analysis.virality_rating` |
| `gemini_analysis` | **ADD** `TEXT` | full JSON from the seed-analysis prompt |
| `performed` | **STOP USING** | left in DB (nullable); removed from model/schema/frontend |
| everything else | keep | filename, platform, niche, view_count, like_count, notes, posted_at, created_at |

### `user_analyses`
| field | change | notes |
|---|---|---|
| `mode` | **ADD** `TEXT DEFAULT 'quick'` | stores the **effective** mode that actually ran |
| everything else | unchanged | |

No new tables. The creator channel profile is computed live from `user_analyses`.

---

## 3. The three modes

| Mode | Context injected | Who | Approx (warm) |
|---|---|---|---|
| **Quick** | raw video only | everyone incl. guests | ~20s |
| **Thinking** | video + global seed library (high + low buckets) | logged-in | ~30s |
| **Deep Thinking** | video + seed library + creator channel profile | logged-in, ≥2 past analyses | ~35s |

### Effective-mode resolution (server-side, authoritative)

```python
def resolve_mode(requested, user, seeds, channel_profile):
    # seeds = combined high+low list (falsy if empty)
    # channel_profile = string, or None if <2 qualifying analyses
    if user is None:
        return "quick"                                   # guest forced
    if requested == "deep_thinking" and channel_profile:
        return "deep_thinking"                           # profile present
    if requested in ("thinking", "deep_thinking") and seeds:
        return "thinking"                                # seeds but no profile
    return "quick"
```

- `_build_channel_profile` returns `None` (never `""`) below threshold.
- Store the **returned** value in `user_analyses.mode`.
- API response returns effective `mode` (+ optional `requested_mode`) so the UI
  badge reflects what actually ran — it can never overclaim "Personalized".

---

## 4. Seed pipeline + seed-analysis prompt

### Flow (`add_seed_video`, synchronous)
1. Admin submits: platform, niche, view_count, like_count, notes?, posted_at?
2. Save video to disk.
3. Call `analyze_seed_video()` (reuses the proven upload→poll-ACTIVE→generate
   pattern from `analyze_video`, and reuses `_PLATFORM_CONTEXT`).
4. On success: store `gemini_analysis` JSON, extract+clamp `rating` (0–10).
5. **Delete the video file.**
6. Return the full analysis to the admin panel for inline review.
7. **On bad JSON or missing `virality_rating`: do NOT persist the row** — return an
   error so the admin retries. A seed with null rating must never be created.

No regenerate endpoint. "Redo a seed" = delete + re-upload.

### Seed-analysis prompt (label is NOT written by the model — see §5)

```
You are building a performance reference library for a video scoring AI.
This analysis is NOT user-facing — it will be read by another AI instance when
scoring new creator videos. Write everything with that reader in mind: specific,
causal, pattern-focused. Never use vague descriptors.

This is a {platform} video in the {niche} niche.
It received {view_count} views and {like_count} likes.

PLATFORM CONTEXT ({platform}):
Distribution surface: {algorithm}
Key engagement signals: {signals}
{platform_tips}

Your job: explain exactly WHY it performed this way. What specific elements caused
these results? What should a future AI look for — or warn against — when it sees
similar patterns in a new video?

SCORING RULES (0–10):
- virality_rating: anchor directly to the view/like count as evidence. 2M views =
  proof of 8–9. 800 views = proof of 1–3. Score what the data confirms.
- hook_strength: did the first 1–3 seconds eliminate the viewer's reason to scroll?
- pacing_score: do cuts and energy sustain watch time to the end?
- audio_score: does the sound serve the content or fight it?
- visual_score: framing, lighting, on-screen text, production quality.
- trend_alignment: is this riding a current format, sound, or topic trend on {platform}?

SEED SUMMARY RULES — most important field, target 150 words:
- Written entirely for AI consumption — never for a human reader.
- Lead with the single most causally important factor driving performance.
- Be precise: not "good hook" but "creator displays the end result in frame 1
  before any explanation, removing the viewer's reason to scroll".
- Explain causality: not just what happened but why it produced this specific
  outcome given {platform}'s algorithm.
- Close with 1–2 sentences telling a future AI exactly what to look for or flag
  when it sees similar patterns in a new video.
- Do NOT write a "high/low performer" label — that is applied separately.

Return ONLY valid JSON:
{
  "virality_rating": <0-10>,
  "hook_strength": <0-10>,
  "pacing_score": <0-10>,
  "audio_score": <0-10>,
  "visual_score": <0-10>,
  "trend_alignment": <0-10>,
  "what_happens": "<2-3 sentences: literal events start to finish, no evaluation>",
  "performance_reason": "<3-4 sentences: causal explanation for exactly why this
    got {view_count} views and {like_count} likes. Name the elements that drove
    or killed distribution.>",
  "patterns": {
    "replicate": ["<pattern worth copying, as an instruction>", "<pattern 2>"],
    "avoid":     ["<pattern to warn against, as a flag>", "<pattern 2>"]
  },
  "seed_summary": "<150 words, AI-consumption only, causal and self-contained.>"
}
```

---

## 5. Seed selection / bucketing (kills the label-contradiction by construction)

The HIGH/LOW label is **derived in code from `rating`**, never written by Gemini.
Buckets use disjoint thresholds, so overlap is impossible.

```python
def select_seed_examples(pool_for_platform, niche):
    niche_seeds = [s for s in pool_for_platform if s.niche == niche]
    pool = niche_seeds if len(niche_seeds) >= 6 else pool_for_platform
    high = [s for s in pool if s.rating is not None and s.rating >= 6]
    low  = [s for s in pool if s.rating is not None and s.rating <= 4]
    high.sort(key=lambda s: (s.rating, s.view_count * recency_mult(s)), reverse=True)
    low.sort(key=lambda s:  (s.rating, s.view_count * recency_mult(s)))
    return high[:10], low[:10]
```

- `rating == 5` or `None` → neither bucket (dormant; don't seed average videos).
- Recency is **only** an intra-rating tiebreaker — it can never move a video
  between buckets (that was the original bug).
- Injection format (label computed from rating):
  `[HIGH PERFORMER | Fitness | 1,800,000 views | 420,000 likes | Rating 9/10]` + summary.
- Empty bucket → omit that section from the prompt.

---

## 6. Creator channel profile (grounded in real data, framed honestly)

Computed live from `user_analyses` for (user, platform). Returns `None` if
<2 total analyses (→ Deep degrades to Thinking).

Two clearly-separated tiers:

**A. Verified performance** — only rows where `actual_views IS NOT NULL`.
- Compute typical view range (median or min–max) + typical likes.
- Only if ≥2 such rows. This is the **gold anchor** for predictions.

**B. Self-assessment trends** — from `scores_json` (the system's own past opinions):
- `avg_score` = mean of `overall_score`.
- `score_trend` = mean(last 3) vs mean(prev 3) → improving / declining / flat
  (only if ≥6 analyses).
- recurring weakness: a dimension scoring ≤4 in >50% of analyses (min 3 samples).
- recurring strength: a dimension scoring ≥7 in >50% of analyses (min 3 samples).
- Dimensions: `hook_strength, pacing_score, audio_score, caption_score, trend_alignment`.

**Degradation:**
- ≥2 analyses but <2 with `actual_views`: trends only + explicit line:
  *"No verified real-world results logged yet — calibrate conservatively against
  global benchmarks, not a personal baseline."*

**Guards:** every `scores_json` parse try/excepted; all divisions guarded.

**`recent_history`** items: `niche · overall_score · actual_views (or "not logged")
· top strength dim · top weakness dim`. **Excludes past predicted_views** so the AI
never anchors to its own prior guesses.

Injected block frames tier B explicitly as *the system's own prior scoring* — used
to flag recurring patterns, NOT as external validation.

---

## 7. Master user-analysis prompt (mode-conditional)

Base identity (all modes):
```
You are an {analyst_title}. Give BRUTALLY HONEST, unfiltered feedback. Creators
use Surge because they want the truth — not validation. Every score and prediction
must be earned.
```

Thinking + Deep — global seed block:
```
GLOBAL PERFORMANCE REFERENCE ({platform} — {niche / all niches}):
Real videos with verified performance data. When you identify a pattern in the
user's video, ask: does this match HIGH PERFORMERS or LOW PERFORMERS? Name the
connection explicitly in analysis_summary.

── HIGH PERFORMERS — what made these succeed ──
[HIGH PERFORMER | {niche} | {views} views | {likes} likes | Rating {rating}/10]
{seed_summary}
... (≤10)

── LOW PERFORMERS — what caused these to fail ──
[LOW PERFORMER | {niche} | {views} views | {likes} likes | Rating {rating}/10]
{seed_summary}
... (≤10)
```

Deep only — channel profile block: the string from §6.

All modes — scoring rules (0–10) + calibration (unchanged from current):
0–2 failing · 3–4 poor · 5 dead average · 6 slightly above · 7 solid · 8 strong ·
9 near-viral (rare) · 10 never. First video=2–3 · regular poster=4–5 ·
50k–200k=6–7 · 500k+=8–9 · when in doubt score LOWER.

Thinking + Deep add — REFERENCE CALIBRATION: ground scores/predictions in the
reference data; reward HIGH-PERFORMER patterns, penalize LOW; name the connection
in analysis_summary; if it matches nothing, say so.

Platform context + video details (caption/bio/profile blocks) — unchanged.

Analysis instructions — unchanged (independent dimension scoring, no-caption=1,
specific-to-THIS-video improvements, before→after examples, caption_rewrite,
hook_rewrite, honest projected_*).

`predicted_views` by mode:
- **Quick:** use training knowledge; most videos <5k; err low.
- **Thinking:** anchor to GLOBAL PERFORMANCE REFERENCE; most land near low-performer
  territory; never exceed high-performer range unless exceptional; err low.
- **Deep:** anchor to global benchmarks AND this creator's verified history; if their
  typical video gets ~800 views, require clear breakout signals to predict higher;
  err low.

JSON output (unchanged shape):
`overall_score, hook_strength, pacing_score, audio_score, caption_score,
trend_alignment, predicted_views, strengths[], improvements[], verdict,
analysis_summary, improvement_plan[], caption_rewrite, hook_rewrite,
projected_verdict, projected_views`.

> Note: `predicted_views` stays free text. Nothing in the system does arithmetic on
> it (channel profile uses `actual_views`; sanity check uses raw ints), so no numeric
> field is needed.

---

## 8. Backend changes per file

- **`models.py`** — `SeedVideo`: add `rating`, `gemini_analysis`; remove `performed`.
  `UserAnalysis`: add `mode`.
- **`schemas.py`** — `SeedVideoOut`: add `rating`, drop `performed`. `AnalysisOut`/
  summary: add `mode`. (seed-analysis JSON is internal, not a response model.)
- **`services/seed_analysis.py`** (new) — `analyze_seed_video(path, platform, niche,
  view_count, like_count) -> dict`; seed prompt; reuse `_PLATFORM_CONTEXT` + the
  upload/poll/generate/delete pattern; `_error_dict`-style guard.
- **`services/gemini.py`** — `_build_system_prompt(..., mode, high_seeds, low_seeds,
  channel_profile)`; conditional global/profile blocks; derive HIGH/LOW labels from
  rating; mode-specific `predicted_views` text.
- **`routers/admin.py`** — `add_seed_video` triggers `analyze_seed_video`, stores
  result, deletes file, returns analysis; drop `performed` Form field + the
  `from-url` `performed = view_count >= 10000` line; remove regenerate (none).
- **`routers/analyze.py`** — accept `mode` Form (default `"quick"`); `resolve_mode`;
  load seeds via `select_seed_examples`; build channel profile only for deep+auth+≥2;
  store effective mode; return effective mode; hard-block feedback validation (§10).
- **channel profile helper** — `_build_channel_profile(user_id, platform, db)` in
  `analyze.py` or `utils.py`; returns `str | None`.

---

## 9. Frontend changes per file

- **`lib/api.ts`** — `analyzeVideo` adds `mode`; `SeedVideoOut` add `rating`, drop
  `performed`; `AnalysisOut`/summary add `mode`; `addSeedVideo`/`seedFromUrl` drop
  `performed`.
- **`components/UploadZone.tsx`** — mode selector for logged-in users (remember last
  choice in localStorage); **guests skip the modal** → default Quick with a single
  inline "Sign in for Thinking / Deep Thinking" link (no lock-wall every upload);
  pass selected `mode` to `analyzeVideo`. Time copy: "~20s once warmed".
- **`app/results/[id]/page.tsx`** — badge from effective `mode`
  ("Quick" / "Thinking" / "Deep Thinking — Personalized"); if degraded, optional
  "ran as Thinking — needs 2+ analyses for Personalized".
- **`app/admin/page.tsx`** — remove `performed` checkbox; add read-only `rating`
  column; expandable row showing `seed_summary`; "Analyzing…" skeleton during the
  sync upload.

---

## 10. Feedback validation (hard blocks only — soft flag cut from v1)

At `PATCH /api/analyses/{id}/feedback`, reject `400` on pure-int checks:
- `actual_views < 0`
- `actual_likes < 0`
- `actual_likes > actual_views`
- `actual_views > 500_000_000`

No flag column, no login-time prompt machinery.

---

## 11. Deploy runbook (ordered — no missing-column window)

1. Run Neon migration SQL (§1). App stays up on old code.
2. `services/seed_analysis.py`.
3. `models.py` / `schemas.py` / `lib/api.ts` field changes.
4. `routers/admin.py` + admin panel UI.
5. `_build_channel_profile()` (+ unit test with mock rows).
6. `services/gemini.py` three-mode builder.
7. `routers/analyze.py` mode handling + feedback validation.
8. Frontend mode selector + results badge.
9. **Deploy backend + frontend together.**
10. `DELETE FROM seed_videos;` then re-upload curated seeds via the new pipeline.
11. End-to-end test (§12).

(Between 9 and 10, old rating-less seeds are auto-ignored — no crash, modes just
run shallow until reseeded.)

---

## 12. Test matrix

| Case | Expect |
|---|---|
| Guest, requests Deep | runs Quick; badge "Quick" |
| Logged-in, 0 seeds, requests Thinking | runs Quick (no seeds) |
| Logged-in, seeds exist, requests Thinking | runs Thinking; seeds in prompt |
| Logged-in, <2 analyses, requests Deep | runs Thinking; badge not "Personalized" |
| Logged-in, ≥2 analyses + actual_views, Deep | runs Deep; verified range in profile |
| Logged-in, ≥2 analyses, no actual_views, Deep | runs Deep; "no verified results" line |
| Seed upload, good video | rating + summary stored, file deleted, shown inline |
| Seed upload, Gemini returns bad JSON | no row created, admin sees error |
| Pool has only 8 seeds | high/low buckets, no overlap, no crash |
| All seeds rated ≥6 | LOW section omitted cleanly |
| Feedback: likes > views | 400 rejected |
| Feedback: views = 9e8 | 400 rejected |

---

## 13. v1 non-goals / known constraints

- **Soft-flag / next-login correction prompt** — deferred (hard blocks only).
- **Seed video durability** — none by design; durable artifact is `gemini_analysis`
  in Postgres. Re-seeding requires the operator's local files.
- **Sync seed analysis blocks the single Render worker** (~20–30s). Off-peak only;
  multi-worker is a paid-tier concern.
- **Gemini context caching** for the shared seed block — possible future cost
  optimization, not in v1.
- **Seed dims (`visual_score`) ≠ user dims (`caption_score`)** — intentional; summary
  is prose, so no code assumes alignment.
```

