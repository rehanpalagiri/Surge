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
    view_count = Column(Integer, nullable=False)
    like_count = Column(Integer, nullable=False)
    performed = Column(Boolean, nullable=False)
    notes = Column(Text, nullable=True)
    posted_at = Column(DateTime, nullable=True)
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
    created_at = Column(DateTime, default=datetime.utcnow)


class FetchStatus(Base):
    __tablename__ = "fetch_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ok = Column(Boolean, nullable=False)
    message = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    acknowledged = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
