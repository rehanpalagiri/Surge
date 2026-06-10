from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, index=True, nullable=False)
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
    niche = Column(String, nullable=False)
    caption = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    scores_json = Column(Text, nullable=False)
    verdict = Column(String, nullable=False)
    actual_views = Column(Integer, nullable=True)
    actual_likes = Column(Integer, nullable=True)
    # Link to the user's posted TikTok video (v1.19). When set, actual_views /
    # actual_likes were auto-fetched from the platform and can be refreshed.
    video_url = Column(String, nullable=True)
    counts_fetched_at = Column(DateTime, nullable=True)
    # Set once this analysis's verified video has been auto-promoted into the seed
    # library (v1.20). Idempotency guard — a non-NULL value means "already a seed".
    promoted_seed_id = Column(Integer, nullable=True)
    # The EFFECTIVE mode that actually ran ("quick" | "thinking" | "deep_thinking").
    # May differ from what the user requested if the run degraded (e.g. Deep with
    # no channel profile → Thinking). The results badge reads this.
    mode = Column(String, nullable=True, default="quick")
    created_at = Column(DateTime, default=datetime.utcnow)


class FetchStatus(Base):
    __tablename__ = "fetch_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ok = Column(Boolean, nullable=False)
    message = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    acknowledged = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
