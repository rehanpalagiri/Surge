from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from database import get_db
from models import (
    AnalysisArtifact, EmailVerificationToken, OutcomeCollectionJob, OutcomeSnapshot,
    PasswordResetToken, UsageEvent, User, UserAnalysis, UserProfile,
)
from schemas import ConsentIn
from auth import require_user, hash_password_async, verify_password_async, is_minor, create_access_token

router = APIRouter(prefix="/api/me", tags=["settings"])


class ChangeUsernameIn(BaseModel):
    new_username: str
    current_password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.patch("/username")
async def change_username(
    body: ChangeUsernameIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    new = body.new_username.strip()
    if not new or len(new) < 2:
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters.")
    if len(new) > 40:
        raise HTTPException(status_code=400, detail="Username must be 40 characters or fewer.")

    # Verify current password before allowing the change
    if not await verify_password_async(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect current password.")

    # Check uniqueness
    result = await db.execute(select(User).where(User.username == new))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="That username is already taken.")

    user.username = new
    await db.commit()
    return {"username": new}


@router.patch("/password")
async def change_password(
    body: ChangePasswordIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")

    if not await verify_password_async(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect current password.")

    user.password_hash = await hash_password_async(body.new_password)
    # Invalidate every OTHER session (bump the token epoch), then hand this device
    # a fresh token so the user who just changed their password stays signed in.
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    await db.refresh(user)
    return {"ok": True, "access_token": create_access_token(user.id, user.token_version)}


@router.get("/consent")
async def get_consent(user: User = Depends(require_user)):
    minor = is_minor(user)
    return {
        # Minors always read as "no" regardless of what's stored.
        "seed_consent": "no" if minor else (user.seed_consent or "ask"),
        "is_minor": minor,
    }


@router.patch("/consent")
async def update_consent(
    body: ConsentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    if is_minor(user):
        raise HTTPException(
            status_code=403,
            detail="Accounts under 18 are automatically excluded from measurement research.",
        )
    if body.seed_consent not in ("yes", "no", "ask"):
        raise HTTPException(status_code=400, detail="Invalid consent value.")
    user.seed_consent = body.seed_consent
    await db.commit()
    return {"seed_consent": user.seed_consent, "is_minor": False}


class DeleteAccountIn(BaseModel):
    password: str


@router.delete("/account")
async def delete_account(
    body: DeleteAccountIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    if not await verify_password_async(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    # Delete in FK order. Account deletion removes analyses and their measurement
    # artifacts; it does not silently retain them as anonymous research data.
    analysis_ids = select(UserAnalysis.id).where(UserAnalysis.user_id == user.id)
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    # Email-verification codes also FK to users.id (NOT NULL). Missing this delete
    # made db.delete(user) raise a ForeignKeyViolation on Postgres — where FKs are
    # enforced — so deletion failed and NO data was removed. (SQLite dev hid it:
    # FK enforcement is off by default there.)
    await db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))
    await db.execute(delete(UsageEvent).where(UsageEvent.analysis_id.in_(analysis_ids)))
    await db.execute(delete(OutcomeCollectionJob).where(OutcomeCollectionJob.analysis_id.in_(analysis_ids)))
    await db.execute(delete(OutcomeSnapshot).where(OutcomeSnapshot.analysis_id.in_(analysis_ids)))
    await db.execute(delete(AnalysisArtifact).where(AnalysisArtifact.analysis_id.in_(analysis_ids)))
    await db.execute(delete(UserProfile).where(UserProfile.user_id == user.id))
    await db.execute(delete(UserAnalysis).where(UserAnalysis.user_id == user.id))
    await db.delete(user)
    await db.commit()
    return {"ok": True}
