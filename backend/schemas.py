from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class UserProfileIn(BaseModel):
    handle: Optional[str] = None
    display_name: Optional[str] = None
    bio: Optional[str] = None
    target_audience: Optional[str] = None
    niche: Optional[str] = None


class UserProfileOut(BaseModel):
    id: int
    user_id: int
    platform: str
    handle: Optional[str]
    display_name: Optional[str]
    bio: Optional[str]
    target_audience: Optional[str]
    niche: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SeedVideoCreate(BaseModel):
    platform: str = "tiktok"
    niche: str
    view_count: Optional[int] = None  # NULL for Instagram (platform hides views)
    like_count: int
    notes: Optional[str] = None


class SeedVideoOut(BaseModel):
    id: int
    filename: str
    platform: str
    niche: str
    view_count: Optional[int] = None  # NULL for Instagram seeds
    like_count: int
    rating: Optional[int] = None
    gemini_analysis: Optional[str] = None  # raw JSON string; admin panel parses seed_summary
    notes: Optional[str]
    posted_at: Optional[datetime] = None
    source: Optional[str] = "admin"  # "admin" | "user" (auto-promoted from a verified link)
    created_at: datetime

    class Config:
        from_attributes = True


class AnalysisOut(BaseModel):
    id: int
    platform: Optional[str] = "tiktok"
    filename: str
    project_name: Optional[str] = None
    niche: str
    caption: Optional[str]
    bio: Optional[str]
    scores_json: Any
    verdict: str
    actual_views: Optional[int]
    actual_likes: Optional[int]
    video_url: Optional[str] = None          # posted TikTok link (counts auto-fetched)
    counts_fetched_at: Optional[datetime] = None
    # v1.24: owner's seed_consent was "ask" — results page shows the consent banner
    pending_seed_consent: bool = False
    # #4: Surge wasn't confident about the niche (routed to the generic rubric) —
    # frontend can prompt the user to confirm/correct it. Mirrors scores_json.
    niche_needs_confirmation: bool = False
    mode: Optional[str] = "quick"  # effective mode that ran
    # Update lineage: None = original upload; int = newer version of parent.
    parent_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OutcomeSnapshotOut(BaseModel):
    id: int
    analysis_id: int
    platform: str
    source: str
    observed_at: datetime
    posted_at: Optional[datetime] = None
    post_age_hours: Optional[int] = None
    horizon: Optional[str] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    saves: Optional[int] = None
    creator_followers: Optional[int] = None
    metric_version: str
    integrity_flags_json: Optional[str] = None

    class Config:
        from_attributes = True


class FeedbackIn(BaseModel):
    actual_views: Optional[int] = None  # None for Instagram (platform hides views)
    actual_likes: Optional[int] = None
    post_age_hours: Optional[int] = None  # user-asserted capture age for manual observations


class VideoLinkIn(BaseModel):
    # None = refresh counts from the already-stored video_url
    url: Optional[str] = None
    # Used only when the provider does not return a trustworthy post timestamp.
    post_age_hours: Optional[int] = None


class SignupIn(BaseModel):
    email: str
    username: str
    password: str
    birth_date: str  # ISO format YYYY-MM-DD; birth_year is derived server-side


class LoginIn(BaseModel):
    # Accepts EITHER a username or an email in the same field (v1.24).
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    birth_year: Optional[int] = None
    birth_date: Optional[str] = None
    seed_consent: Optional[str] = "ask"
    is_minor: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class ConsentIn(BaseModel):
    seed_consent: str  # "yes" | "no" | "ask"


class SeedConsentDecisionIn(BaseModel):
    allow: bool
    # Optional: persist the choice as the account-wide setting ("yes" | "no").
    remember: Optional[str] = None


class ForgotPasswordIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str


class VerifyResetCodeIn(BaseModel):
    token: str


class DeleteAccountIn(BaseModel):
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AnalysisSummaryOut(BaseModel):
    id: int
    platform: str
    project_name: Optional[str] = None
    niche: str
    verdict: str
    caption_preview: Optional[str] = None
    actual_views: Optional[int] = None
    actual_likes: Optional[int] = None
    video_url: Optional[str] = None
    counts_fetched_at: Optional[datetime] = None
    mode: Optional[str] = "quick"
    parent_id: Optional[int] = None
    created_at: datetime


class ScoreResult(BaseModel):
    hook_velocity: int
    cut_frequency: int
    text_scannability: int
    curiosity_gap: int
    audio_visual_sync: int
    loop_seamlessness: int
    strengths: list[str]
    improvements: list[str]
    verdict: str
    analysis_summary: str
    improvement_plan: list[Any] = []
    hook_rewrite: Optional[str] = None
    caption_rewrite: Optional[str] = None
    recommended_experiment: Optional[dict[str, str]] = None
