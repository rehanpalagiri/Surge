from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class TrendSummary(Base):
    __tablename__ = "trend_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String, nullable=False)
    niche = Column(String, nullable=False)
    trend_text = Column(Text, nullable=False)
    recent_seed_count = Column(Integer, nullable=False)
    established_seed_count = Column(Integer, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("platform", "niche", name="uq_platform_niche_trend"),)


class NicheInsight(Base):
    __tablename__ = "niche_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String, nullable=False)   # "tiktok" | "instagram"
    niche = Column(String, nullable=False)       # canonical niche
    insight = Column(Text, nullable=False)       # synthesized pattern block
    seed_count = Column(Integer, nullable=False) # how many seeds were analyzed
    generated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("platform", "niche", name="uq_platform_niche_insight"),)


class CalibrationNote(Base):
    """Mistake-summarization (Build #3). Aggregates safe-to-learn-from corrections
    (from audit_prediction) into a bounded calibration nudge per (platform, niche),
    or the literal "GLOBAL" pseudo-niche. Regenerated FROM SCRATCH each run — never
    stacked — and every adjustment is clamped server-side before storage. Parallel to
    NicheInsight; additive new table (auto-created by create_all)."""

    __tablename__ = "calibration_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String, nullable=False)   # "tiktok" | "instagram"
    niche = Column(String, nullable=False)       # canonical niche, or "GLOBAL"
    note_json = Column(Text, nullable=False)     # clamped calibration note (see services/calibration.py)
    sample_count = Column(Integer, nullable=False)  # how many safe corrections fed this note
    generated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("platform", "niche", name="uq_platform_niche_calibration"),)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, index=True, nullable=False)
    # v1.24: email is the primary login identifier; username stays as display name.
    # Nullable so pre-1.24 accounts keep working (they log in with username).
    email = Column(String, unique=True, nullable=True)
    # Age gate: birth_date (YYYY-MM-DD) is the authoritative field; birth_year is
    # kept for backward compat with pre-DOB accounts. is_minor() prefers birth_date.
    birth_year = Column(Integer, nullable=True)
    birth_date = Column(String, nullable=True)  # ISO format YYYY-MM-DD
    # Seed-pool consent: "yes" | "no" | "ask". Minors (13–17) are forced to "no"
    # and can never change it; adults default to "ask" (decide per linked video).
    seed_consent = Column(String, nullable=True, default="ask")
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SeedVideo(Base):
    __tablename__ = "seed_videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False)
    platform = Column(String, nullable=False, default="tiktok")  # "tiktok" | "instagram"
    niche = Column(String, nullable=False)
    view_count = Column(Integer, nullable=True)   # NULL for Instagram (platform hides views)
    like_count = Column(Integer, nullable=False)
    # Virality rating (0–10) extracted from the Gemini seed analysis. Nullable so
    # pre-1.13 seeds (no rating) are simply ignored by the bucketer until reseeded.
    rating = Column(Integer, nullable=True)
    # Full JSON from the seed-analysis prompt — the durable artifact (the video
    # file itself is deleted after analysis). Read back into the scoring prompt.
    gemini_analysis = Column(Text, nullable=True)
    # DEPRECATED (v1.13): no longer used. Kept as a column with default=False so
    # SQLAlchemy always supplies a value on INSERT — this satisfies the existing
    # NOT NULL constraint on the production Postgres table without a manual
    # `ALTER COLUMN ... DROP NOT NULL` migration. Do not read this field.
    performed = Column(Boolean, nullable=True, default=False)
    notes = Column(Text, nullable=True)
    posted_at = Column(DateTime, nullable=True)
    # Provenance (v1.20): "admin" = hand-curated via /admin, "user" = auto-promoted
    # from a verified user-posted video (real tikwm-fetched counts). User seeds are
    # the better signal — real outcomes, not a curator's guess — and this column lets
    # the bucketer weight them higher later. Defaults to "admin" for pre-1.20 rows.
    source = Column(String, nullable=True, default="admin")
    created_at = Column(DateTime, default=datetime.utcnow)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(String, nullable=False)          # "tiktok" | "instagram"
    handle = Column(String, nullable=True)             # @username on the platform
    display_name = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    target_audience = Column(Text, nullable=True)      # who they're trying to reach
    niche = Column(String, nullable=True)              # their primary content niche
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "platform", name="uq_user_platform"),)


class UserAnalysis(Base):
    __tablename__ = "user_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    platform = Column(String, nullable=True, default="tiktok")  # "tiktok" | "instagram"
    filename = Column(String, nullable=False)
    # Creator-facing label for grouping an upload and its later updates.
    # Nullable for analyses created before project naming existed.
    project_name = Column(String, nullable=True)
    niche = Column(String, nullable=False)  # the user's own words (display, shown in My Projects)
    # The canonical niche the classifier resolved (or "Uncategorized"). It provides
    # craft context without exposing the prompt to arbitrary free-text labels.
    canonical_niche = Column(String, nullable=True)
    caption = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    scores_json = Column(Text, nullable=False)
    correction_json = Column(Text, nullable=True)
    # Legacy calibration compatibility. New craft reviews always store 0.
    calibration_version = Column(Integer, nullable=True, default=0)
    verdict = Column(String, nullable=False)
    actual_views = Column(Integer, nullable=True)
    actual_likes = Column(Integer, nullable=True)
    # Link plus latest-count cache for list views. Immutable observations live in
    # outcome_snapshots and are the only source for maturity-window comparisons.
    video_url = Column(String, nullable=True)
    counts_fetched_at = Column(DateTime, nullable=True)
    # Legacy seed-promotion fields. New craft reviews are never promoted into the
    # live evaluator and outcomes never calibrate its response.
    promoted_seed_id = Column(Integer, nullable=True)
    pending_seed_consent = Column(Boolean, nullable=True, default=False)
    # New rows use "craft_review". Historical quick/thinking/deep values remain readable.
    mode = Column(String, nullable=True, default="quick")
    # Async analysis lifecycle: "pending" → "processing" → "complete" | "error".
    # Defaults to "complete" so all pre-existing rows are treated as finished.
    status = Column(String, nullable=True, default="complete")
    # Update lineage: points to the analysis this version was created to improve.
    # NULL = original upload; non-NULL = user clicked "Update" on an old result.
    parent_id = Column(Integer, ForeignKey("user_analyses.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalysisArtifact(Base):
    """Stable dataset identity for an analyzed upload.

    Exact hashes are populated now; perceptual/audio fingerprints are reserved for
    the near-duplicate detector so future dataset splits can keep related assets
    together without changing the analysis table again.
    """

    __tablename__ = "analysis_artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("user_analyses.id"), nullable=False, unique=True)
    content_sha256 = Column(String, nullable=True, index=True)
    platform_post_id = Column(String, nullable=True, index=True)
    creator_key = Column(String, nullable=True, index=True)
    perceptual_hash = Column(String, nullable=True, index=True)
    audio_fingerprint = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class OutcomeSnapshot(Base):
    """Immutable observation of a posted video's public metrics.

    `horizon` is set only when post age can be calculated and the observation is
    close enough to a supported maturity window. Raw snapshots remain useful even
    when they miss a target window, but must not be mixed across ages in evaluation.
    """

    __tablename__ = "outcome_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("user_analyses.id"), nullable=False, index=True)
    platform = Column(String, nullable=False)
    source = Column(String, nullable=False)
    observed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    posted_at = Column(DateTime, nullable=True)
    post_age_hours = Column(Integer, nullable=True)
    horizon = Column(String, nullable=True, index=True)  # "24h" | "7d" | "30d" | NULL
    views = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)
    comments = Column(Integer, nullable=True)
    shares = Column(Integer, nullable=True)
    saves = Column(Integer, nullable=True)
    creator_followers = Column(Integer, nullable=True)
    metric_version = Column(String, nullable=False, default="observed_response_v1")
    provider_payload_hash = Column(String, nullable=True)
    integrity_flags_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OutcomeCollectionJob(Base):
    """Durable request for one fixed-maturity public-metric observation."""

    __tablename__ = "outcome_collection_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("user_analyses.id"), nullable=False, index=True)
    horizon = Column(String, nullable=False)  # "24h" | "7d" | "30d"
    due_at = Column(DateTime, nullable=False, index=True)
    tolerance_hours = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("analysis_id", "horizon", name="uq_analysis_outcome_horizon"),
    )


class UsageEvent(Base):
    """Provider/model usage ledger for latency, unit economics, and reliability."""

    __tablename__ = "usage_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("user_analyses.id"), nullable=True, index=True)
    operation = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    model = Column(String, nullable=True)
    success = Column(Boolean, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    input_bytes = Column(Integer, nullable=True)
    output_bytes = Column(Integer, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost_micros = Column(Integer, nullable=True)
    error_code = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FetchStatus(Base):
    __tablename__ = "fetch_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ok = Column(Boolean, nullable=False)
    message = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    acknowledged = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
