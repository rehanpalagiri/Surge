import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func

from database import get_db
from models import User
from schemas import SignupIn, LoginIn, UserOut, TokenOut
from auth import hash_password, verify_password, create_access_token, require_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_minor(user: User) -> bool:
    """Under 18 by birth year. Legacy accounts (no birth_year) are treated as
    adults — they predate the age gate and were never offered seed consent."""
    if user.birth_year is None:
        return False
    return (datetime.utcnow().year - user.birth_year) < 18


def user_to_out(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "birth_year": user.birth_year,
        "seed_consent": user.seed_consent or "ask",
        "is_minor": is_minor(user),
        "created_at": user.created_at,
    }


@router.post("/signup", response_model=TokenOut)
async def signup(payload: SignupIn, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    username = payload.username.strip()

    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    current_year = datetime.utcnow().year
    if payload.birth_year < 1900 or payload.birth_year > current_year:
        raise HTTPException(status_code=400, detail="Please enter a valid birth year.")
    age = current_year - payload.birth_year
    if age < 13:
        raise HTTPException(status_code=403, detail="You must be 13 or older to use Surge.")

    existing_email = await db.execute(
        select(User).where(func.lower(User.email) == email)
    )
    if existing_email.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered.")

    existing_name = await db.execute(select(User).where(User.username == username))
    if existing_name.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken.")

    # 13–17: seed consent is permanently "no" (enforced again in the consent
    # endpoint and in seed_promote — defense in depth). 18+: default "ask".
    consent = "no" if age < 18 else "ask"

    user = User(
        username=username,
        email=email,
        birth_year=payload.birth_year,
        seed_consent=consent,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return TokenOut(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    ident = payload.username.strip()
    # One field, two identifiers: match against username OR email (v1.24).
    result = await db.execute(
        select(User).where(
            or_(User.username == ident, func.lower(User.email) == ident.lower())
        )
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(require_user)):
    return user_to_out(user)
