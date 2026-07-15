import asyncio
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


async def hash_password_async(password: str) -> str:
    # bcrypt is CPU-bound and releases the GIL during hashing, so a worker thread
    # runs it truly in parallel and keeps the single event loop free for other
    # requests (prod is WEB_CONCURRENCY=1 — one hash inline stalls the whole API).
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(verify_password, password, password_hash)


def create_access_token(user_id: int, token_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        # Session epoch. Bumped on password change/reset so any token minted
        # before the change stops validating (see require_user). Legacy tokens
        # carry no "ver" claim and are treated as version 0.
        "ver": int(token_version or 0),
        "iat": now,
        "exp": now + timedelta(days=TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> Optional[dict]:
    """Verify signature + expiry with the algorithm pinned, and return the claims,
    or None on any failure. An ``alg=none`` / wrong-algorithm / expired / tampered
    token is rejected here."""
    try:
        return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def _token_matches_user(payload: dict, user: User) -> bool:
    """The token's session epoch ("ver") must equal the user's current
    token_version. A password change/reset increments token_version, which
    invalidates every JWT issued before it."""
    try:
        return int(payload.get("ver", 0) or 0) == int(user.token_version or 0)
    except (TypeError, ValueError):
        return False


async def _user_from_token(authorization: Optional[str], db: AsyncSession) -> Optional[User]:
    token = _extract_token(authorization)
    payload = _decode_token(token) if token else None
    if not payload:
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not _token_matches_user(payload, user):
        return None
    return user


async def require_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _user_from_token(authorization, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def optional_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    return await _user_from_token(authorization, db)
