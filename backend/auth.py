import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import jwt
import bcrypt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import User

JWT_ALGORITHM = "HS256"
TOKEN_TTL_DAYS = 30


def is_minor(user: User) -> bool:
    """Under 18 by exact date when available; falls back to year for legacy accounts.
    This is the single authoritative implementation — import from here, don't reimplement.
    """
    today = date.today()
    if user.birth_date:
        try:
            bd = date.fromisoformat(user.birth_date)
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            return age < 18
        except ValueError:
            pass
    if user.birth_year is None:
        return False
    return (today.year - user.birth_year) < 18


# Stripe subscription statuses that grant Pro access. "past_due" is included as
# a grace period: Stripe keeps the subscription live while it retries the card,
# and only emits customer.subscription.deleted once it finally gives up — at
# which point the webhook flips the status to "canceled" and access ends.
PRO_STATUSES = frozenset({"active", "trialing", "past_due"})


def _comp_emails() -> frozenset[str]:
    """Operator allowlist of emails that get Pro for free (owner/testers/comps).

    Read live from COMP_PRO_EMAILS (comma-separated) so it can be changed in the
    Railway dashboard without a code change. SERVER-SIDE ONLY — a user can never
    add themselves; email uniqueness at signup means only the real holder of a
    listed address can occupy it. Put only addresses you control here.
    """
    raw = os.getenv("COMP_PRO_EMAILS", "")
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


def is_comp(user: "User") -> bool:
    """True when this user gets Pro via the operator comp allowlist (no Stripe)."""
    if user is None or not user.email:
        return False
    return user.email.strip().lower() in _comp_emails()


def is_pro(user: "User") -> bool:
    """True when the user has Pro access — either a paid Stripe subscription OR an
    operator comp grant.

    Source of truth for PAID access = the Stripe-webhook-written
    subscription_status (never client input). Comp access = the COMP_PRO_EMAILS
    allowlist. Import from here; don't reimplement.
    """
    if user is None:
        return False
    if is_comp(user):
        return True
    return (user.subscription_status or "") in PRO_STATUSES


def _secret() -> str:
    return os.getenv("JWT_SECRET", "dev-insecure-secret-change-me")


def hash_password(password: str) -> str:
    # bcrypt only considers the first 72 bytes; truncate to avoid a ValueError.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:72], password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except Exception:
        return None


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


async def require_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_token(authorization)
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def optional_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    token = _extract_token(authorization)
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
