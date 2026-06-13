from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from database import get_db
from models import UserProfile, UserAnalysis, PasswordResetToken, User
from schemas import UserProfileIn, UserProfileOut, DeleteAccountIn
from auth import require_user, verify_password

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
        profile.updated_at = datetime.utcnow()
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


@router.delete("/account")
async def delete_account(
    payload: DeleteAccountIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    # Delete in FK order to avoid constraint violations
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    await db.execute(delete(UserProfile).where(UserProfile.user_id == user.id))
    await db.execute(delete(UserAnalysis).where(UserAnalysis.user_id == user.id))
    await db.delete(user)
    await db.commit()
    return {"ok": True}
