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
    niche: str
    view_count: int
    like_count: int
    performed: bool
    notes: Optional[str] = None


class SeedVideoOut(BaseModel):
    id: int
    filename: str
    niche: str
    view_count: int
    like_count: int
    performed: bool
    notes: Optional[str]
    posted_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AnalysisOut(BaseModel):
    id: int
    platform: Optional[str] = "tiktok"
    filename: str
    niche: str
    caption: Optional[str]
    bio: Optional[str]
    scores_json: Any
    verdict: str
    actual_views: Optional[int]
    actual_likes: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackIn(BaseModel):
    actual_views: int
    actual_likes: Optional[int] = None


class SignupIn(BaseModel):
    username: str
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AnalysisSummaryOut(BaseModel):
    id: int
    platform: str
    niche: str
    verdict: str
    overall_score: Optional[int] = None
    predicted_views: Optional[str] = None
    caption_preview: Optional[str] = None
    actual_views: Optional[int] = None
    actual_likes: Optional[int] = None
    created_at: datetime


class ScoreResult(BaseModel):
    overall_score: int
    hook_strength: int
    pacing_score: int
    audio_score: int
    caption_score: int
    trend_alignment: int
    predicted_views: str
    strengths: list[str]
    improvements: list[str]
    verdict: str
    analysis_summary: str
