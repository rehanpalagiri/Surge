# Surge Product Blueprint

Status: implemented locally; not deployed by this task.

## Decision

The algorithm audit did not support a broad performance-prediction product. Likes/views is an observed response rate, not retention or content quality, and it is vulnerable to distribution differences and metric gaming. Surge therefore keeps its name but narrows the product:

> Outcome-blind craft review + fixed-age post experiments.

This is intentionally smaller than “predict what goes viral.” The old aggregate score, predicted counts, performance calibration, and correction loop are retired from live analyses. Legacy columns and offline admin code remain for compatibility but cannot affect a new craft review.

## Live product contract

### AI review

Gemini sees the uploaded media and creator-supplied context, but not seed outcomes, post counts, prior performance, or calibration notes. It returns:

- six independent observable craft assessments;
- concrete evidence and editing hypotheses;
- caption/hook alternatives;
- a qualitative craft verdict; and
- one experiment: change one thing, hold named variables constant, observe a named result.

The system instruction treats all creator/provider content as delimited untrusted data. Output validation strips legacy aggregate and prediction fields.

### Observed outcomes

Published-post observations are stored as immutable snapshots. Each snapshot can contain views, likes, comments, shares, saves, creator followers, capture time, post time, age, source, provider post ID, integrity flags, metric version, and a provider-payload hash.

Maturity labels are assigned only inside explicit windows:

| Label | Target age | Tolerance | Purpose |
|---|---:|---:|---|
| 24h | 24 hours | ±6 hours | early response |
| 7d | 168 hours | ±24 hours | settled short-term response |
| 30d | 720 hours | ±72 hours | longer-tail response |

These are operational collection windows, not minimum sample sizes and not claims of statistical power. Off-window observations remain usable as timestamped history but cannot be compared as if equally mature.

Observed like rate is `likes / views` only when both are present and views is positive. It is descriptive, not causal. Comments are retained as raw public observations but excluded from any quality metric.

## UX migration

- Landing page: “Make Each Post Teach You Something.”
- Result page: AI-assessed craft dimensions, explicit evidence disclaimer, and one next experiment.
- Outcome timeline: separate 24h/7d/30d cards with provenance and integrity labels.
- Experiments page: latest capture is clearly labelled as mixed-age history, with prompts to refresh near fixed windows.
- Sample, social cards, navigation, consent, privacy, terms, email, admin labels, and upsells no longer promise prediction or virality scoring.
- Brand remains **Surge**. No domain, logo, environment, package, or deployment setting changes are required.

## Evaluation design for any future predictive model

No predictive model is approved by this blueprint. Before considering one:

1. Define a platform-specific target with a verified denominator and fixed maturity.
2. Group every post from one creator into the same split to prevent creator leakage.
3. Train on the past and evaluate on later chronological holdouts.
4. Detect exact, perceptual, and audio near-duplicates across every split before fitting.
5. Report missingness, provider provenance, maturity-window compliance, and suspected gaming.
6. Compare against creator-history and simple non-LLM baselines.
7. Report calibration and uncertainty, not only rank correlation.
8. Keep prediction claims distinct from causal claims. Recommended edits require controlled experiments for causal evidence.

No round minimum is specified. Sample size must be derived from a preregistered estimand, baseline variance/event rate, smallest effect worth detecting, alpha, desired power, repeated measures per creator, and expected attrition. For clustered creator data, inflate the independent-sample requirement by the design effect `1 + (m - 1) × ICC`, where `m` is average posts per creator and `ICC` is the measured intra-creator correlation. Without those inputs, a numeric threshold would be fiction.

## Distortion and integrity risks

Public counts may be distorted by purchased engagement, bots, engagement pods, giveaways, rage bait, spam, creator-authored comments, controversial content, deleted posts, edited captions, privacy changes, or platform enforcement. Integrity flags are therefore part of each observation. Surge must not silently “clean” ambiguous cases into causal evidence.

Future duplicate controls must include:

- exact SHA-256 for identical upload bytes;
- perceptual video hashes for crops, re-encodes, overlays, and speed changes;
- audio fingerprints for reused tracks/voiceovers; and
- creator and provider post IDs.

Current implementation captures exact hashes and identity slots. Perceptual/audio matching is a known prerequisite for evaluation, not a completed feature.

## Provider risk register

| Risk | TikWM | HikerAPI | Control |
|---|---|---|---|
| Availability / reliability | third-party endpoint | third-party API | timeouts, visible errors, manual fallback |
| Schema drift | undocumented payload changes | version/product changes | fail closed on required fields, keep optional fields NULL |
| Rate and financial limits | availability may change | plan quota/pricing may change | usage telemetry, no automatic retry storms |
| Legal / platform policy | scraping/ToS uncertainty | data-access/ToS uncertainty | counsel and contract review before scale |
| Data accuracy | public counters may lag | public counters may lag | capture timestamp, source, integrity flags |

Real provider payloads were not available for this local implementation. Optional provider fields are therefore **documented but not runtime-verified**. No external provider calls were made.

## Economics and capacity model

The code records the inputs needed for an evidence-based estimate. The protected admin operations report exposes measured reliability, usage, row counts, and cost-coverage gaps. Do not fill absent measurements with guessed prices.

For one analysis:

`analysis cost = Gemini media input + Gemini output + upload/storage transfer + database writes + allocated infrastructure`

For one refresh:

`refresh cost = provider request fee + database write + allocated infrastructure`

Monthly storage growth:

`new artifact metadata + outcome rows + usage rows + retained upload bytes (if enabled)`

Gross margin:

`(recognized revenue - model cost - provider cost - variable hosting/storage/egress - payment fees) / recognized revenue`

Measure p50/p95/p99 end-to-end latency and provider/model error rates. Segment by platform, upload size, and success. The existing `usage_events` fields cover operation, provider/model, latency, bytes, tokens, success, error class, and nullable verified cost.

Current status:

| Item | Status |
|---|---|
| Per-analysis cost | unverified; requires Gemini billing/token telemetry and hosting allocation |
| Refresh cost | unverified; requires contracted provider pricing and request counts |
| Latency | individual calls instrumented; distribution requires production observations |
| Storage growth | schema measurable; real row/upload growth requires production observations |
| Gross margin | cannot be calculated without price, conversion, and verified variable cost |

## Rollout and rollback

1. Run backend unit/compile checks and frontend typecheck/build.
2. Verify new tables are created in a disposable database.
3. Deploy schema and application in one batched backend release only after explicit approval.
4. Smoke-test upload, anonymous lock, authenticated review, provider/manual capture, maturity labels, deletion, and error handling.
5. Monitor success rate and latency before collecting enough observations for any research claim.

Rollback is application rollback to the prior release. New tables are additive and can remain unused; do not destructively drop them during an incident. Legacy rows remain readable, while new output omits legacy prediction fields.

## Explicit non-goals

- predicting views, likes, reach, retention, or virality;
- claiming an edit caused or will cause better performance;
- treating likes/views or comment count as content quality;
- learning from linked outcomes in the live Gemini review;
- an in-process auto-refresh worker (the protected due-job endpoint still requires an external trusted scheduler); and
- claiming near-duplicate protection before perceptual/audio matching exists.
