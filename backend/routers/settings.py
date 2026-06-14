from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update

from database import get_db
from models import User, UserProfile, UserAnalysis, PasswordResetToken
from schemas import ConsentIn
from auth import require_user, hash_password, verify_password
from routers.auth import is_minor

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
    if not verify_password(body.current_password, user.password_hash):
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
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect current password.")

    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"ok": True}


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
            detail="Accounts under 18 are automatically excluded from platform benchmarks.",
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
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    # Delete in FK order; unlink analyses (keep anonymised data) then remove user.
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    await db.execute(delete(UserProfile).where(UserProfile.user_id == user.id))
    await db.execute(
        update(UserAnalysis).where(UserAnalysis.user_id == user.id).values(user_id=None)
    )
    await db.delete(user)
    await db.commit()
    return {"ok": True}
