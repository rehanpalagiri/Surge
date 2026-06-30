from datetime import datetime
from services.clock import utc_now_naive
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import UserProfile, User
from schemas import UserProfileIn, UserProfileOut
from auth import require_user

router = APIRouter(prefix="/api/me", tags=["profile"])

VALID_PLATFORMS = {"tiktok", "instagram"}


@router.get("/profile/{platform}", response_model=UserProfileOut)
async def get_profile(
    platform: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    if platform not in VALID_PLATFORMS:
        raise HTTPException(status_code=400, detail="platform must be 'tiktok' or 'instagram'")
    result = await db.execute(
        select(UserProfile).where(
            UserProfile.user_id == user.id,
            UserProfile.platform == platform,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/profile/{platform}", response_model=UserProfileOut)
async def upsert_profile(
    platform: str,
    data: UserProfileIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    if platform not in VALID_PLATFORMS:
        raise HTTPException(status_code=400, detail="platform must be 'tiktok' or 'instagram'")

    result = await db.execute(
        select(UserProfile).where(
            UserProfile.user_id == user.id,
            UserProfile.platform == platform,
        )
    )
    profile = result.scalar_one_or_none()

    if profile:
        profile.handle = data.handle
        profile.display_name = data.display_name
        profile.bio = data.bio
        profile.target_audience = data.target_audience
        profile.niche = data.niche
        profile.updated_at = utc_now_naive()
    else:
        profile = UserProfile(
            user_id=user.id,
            platform=platform,
            handle=data.handle,
            display_name=data.display_name,
            bio=data.bio,
            target_audience=data.target_audience,
            niche=data.niche,
        )
        db.add(profile)

    await db.commit()
    await db.refresh(profile)
    return profile
