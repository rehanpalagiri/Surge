import asyncio
import logging
import os
import re
import secrets
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

import aiosmtplib
import certifi
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func

from database import get_db
from models import User, PasswordResetToken
from schemas import SignupIn, LoginIn, UserOut, TokenOut, ForgotPasswordIn, ResetPasswordIn, VerifyResetCodeIn
from auth import hash_password, verify_password, create_access_token, require_user

_RESET_TTL = timedelta(hours=1)
_SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASS", "")
_EMAIL_FROM = os.getenv("EMAIL_FROM", f"Surge <{_SMTP_USER}>" if _SMTP_USER else "")
_FRONTEND_URL = os.getenv("FRONTEND_URL", "https://surge-chi-khaki.vercel.app")

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
async def signup(payload: SignupIn, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
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

    background_tasks.add_task(_send_welcome_email, user.email, user.username)
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


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordIn, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()
    # Always return 200 — never reveal whether the email exists.
    if not user or not user.email:
        return {"ok": True}

    # Invalidate any existing unused tokens for this user.
    existing = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used == False,  # noqa: E712
        )
    )
    for tok in existing.scalars().all():
        tok.used = True

    token = f"{secrets.randbelow(1_000_000):06d}"
    reset = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=datetime.utcnow() + _RESET_TTL,
    )
    db.add(reset)
    await db.commit()

    background_tasks.add_task(_send_reset_email, user.email, user.username, token)
    return {"ok": True}


@router.post("/verify-reset-code")
async def verify_reset_code(payload: VerifyResetCodeIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == payload.token)
    )
    reset = result.scalar_one_or_none()
    if not reset or reset.used or reset.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired code.")
    return {"valid": True}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordIn, db: AsyncSession = Depends(get_db)):
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == payload.token)
    )
    reset = result.scalar_one_or_none()

    if not reset or reset.used or reset.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired code. Please request a new one.")

    user_result = await db.execute(select(User).where(User.id == reset.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="User not found.")

    user.password_hash = hash_password(payload.new_password)
    reset.used = True
    await db.commit()

    return {"ok": True}


async def _send_reset_email(to_email: str, username: str, code: str) -> None:
    if not _SMTP_USER or not _SMTP_PASS:
        return  # not configured — skip silently
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#6d28d9">Surge — Password Reset</h2>
      <p>Hi <strong>{username}</strong>,</p>
      <p>Your password reset code is:</p>
      <p style="margin:24px 0;text-align:center">
        <span style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#6d28d9">{code}</span>
      </p>
      <p style="color:#888;font-size:13px">
        Enter this code on the Surge reset page. It expires in 1 hour.
        If you didn't request this, ignore this email — your password won't change.
      </p>
      <p style="color:#888;font-size:12px">— The Surge team</p>
    </div>
    """
    plain = (
        f"Hi {username},\n\n"
        f"Your Surge password reset code is: {code}\n\n"
        f"It expires in 1 hour. If you didn't request this, ignore this email.\n\n"
        f"— The Surge team"
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your Surge password"
    msg["From"] = _EMAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            await aiosmtplib.send(
                msg,
                hostname=_SMTP_HOST,
                port=_SMTP_PORT,
                username=_SMTP_USER,
                password=_SMTP_PASS,
                start_tls=True,
                timeout=30,
                cert_bundle=certifi.where(),
            )
            logger.info("Reset email sent to %s (attempt %d)", to_email, attempt + 1)
            return
        except Exception as e:
            last_err = e
            logger.warning("Reset email attempt %d failed for %s: %s: %s", attempt + 1, to_email, type(e).__name__, e)
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s

    logger.error("All reset email attempts failed for %s: %s", to_email, last_err)


async def _send_welcome_email(to_email: str, username: str) -> None:
    if not _SMTP_USER or not _SMTP_PASS:
        return
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#6d28d9">Welcome to Surge, {username}!</h2>
      <p>You're all set. Upload your first video and get an AI-powered virality score in seconds.</p>
      <p style="margin:24px 0">
        <a href="{_FRONTEND_URL}"
           style="background:#6d28d9;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">
          Analyse a video →
        </a>
      </p>
      <p style="color:#888;font-size:13px">
        Upgrade to <strong>Thinking</strong> or <strong>Deep</strong> mode for a detailed breakdown
        and personalised tips based on your channel's history.
      </p>
      <p style="color:#888;font-size:12px">— The Surge team</p>
    </div>
    """
    plain = (
        f"Welcome to Surge, {username}!\n\n"
        f"You're all set. Upload your first video at {_FRONTEND_URL} "
        f"and get an AI-powered virality score in seconds.\n\n"
        f"— The Surge team"
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Welcome to Surge 🎬"
    msg["From"] = _EMAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            await aiosmtplib.send(
                msg,
                hostname=_SMTP_HOST,
                port=_SMTP_PORT,
                username=_SMTP_USER,
                password=_SMTP_PASS,
                start_tls=True,
                timeout=30,
                cert_bundle=certifi.where(),
            )
            logger.info("Welcome email sent to %s (attempt %d)", to_email, attempt + 1)
            return
        except Exception as e:
            last_err = e
            logger.warning("Welcome email attempt %d failed for %s: %s: %s", attempt + 1, to_email, type(e).__name__, e)
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s

    logger.error("All welcome email attempts failed for %s: %s", to_email, last_err)
