import asyncio
import html as _html
import logging
import os
import re
import secrets
from datetime import date, datetime, timedelta
from services.clock import utc_now_naive

logger = logging.getLogger(__name__)

import aiosmtplib
import certifi
import httpx
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func

from database import get_db
from models import User, PasswordResetToken, EmailVerificationToken
from schemas import SignupIn, LoginIn, UserOut, TokenOut, ForgotPasswordIn, ResetPasswordIn, VerifyResetCodeIn, VerifyEmailIn, GoogleAuthIn
from auth import hash_password, verify_password, create_access_token, require_user, is_minor
from services.throttle import check_rate, client_ip

_RESET_TTL = timedelta(hours=1)
_SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASS", "")
_EMAIL_FROM = os.getenv("EMAIL_FROM", f"Surge <{_SMTP_USER}>" if _SMTP_USER else "")
_FRONTEND_URL = os.getenv("FRONTEND_URL", "https://surge-chi-khaki.vercel.app")
# Brevo HTTP API key (xkeysib-...). Preferred transport: HTTPS/443 works on hosts
# like Railway that block all outbound SMTP ports (587/2525/465/25). SMTP is the
# local-dev fallback only.
_BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
# Google OAuth client ID (…apps.googleusercontent.com). Set in Railway; the same
# value is exposed to the frontend as NEXT_PUBLIC_GOOGLE_CLIENT_ID.
_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Precomputed bcrypt hash used to equalize login timing when the submitted
# identifier matches no account. Always running a real bcrypt verify (against this
# throwaway hash when there's no user) keeps the not-found path the same cost as
# the wrong-password path, so response time can't be used to enumerate accounts.
_DUMMY_PW_HASH = hash_password("surge-login-timing-equalizer")

# Per-email reset cap (persistent, via the token table's created_at): at most this
# many reset emails per hour to one account — guards a victim's inbox + Brevo quota.
_RESET_PER_EMAIL_HOUR = 3

# Email verification: codes live longer than reset codes (users may verify later),
# and the resend cap protects the inbox + Brevo quota.
_VERIFY_TTL = timedelta(hours=24)
_VERIFY_PER_EMAIL_HOUR = 5


def _client_ip(request: Request) -> str:
    """Throttle key for unauthenticated endpoints. Delegates to the shared,
    spoof-resistant resolver (trusts only proxy hops we control — see
    services.throttle.client_ip). Taking the leftmost X-Forwarded-For entry here
    would let an attacker rotate the header to get unlimited reset/verify guesses."""
    return client_ip(request)


def user_to_out(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "birth_year": user.birth_year,
        "birth_date": user.birth_date,
        "seed_consent": user.seed_consent or "ask",
        "is_minor": is_minor(user),
        "email_verified": bool(user.email_verified),
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

    try:
        bd = date.fromisoformat(payload.birth_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Please enter a valid date of birth.")
    today = date.today()
    if bd > today or bd.year < 1900:
        raise HTTPException(status_code=400, detail="Please enter a valid date of birth.")
    age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
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
        birth_year=bd.year,
        birth_date=payload.birth_date,
        seed_consent=consent,
        password_hash=hash_password(payload.password),
        email_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Email verification: send a 6-digit code now; the welcome email waits until
    # they confirm (in /verify-email). They still get a token so the verify step
    # is authenticated.
    code = await _issue_verification_code(user.id, db)
    background_tasks.add_task(_send_verification_email, user.email, user.username, code)
    return TokenOut(access_token=create_access_token(user.id, user.token_version or 0))


async def _issue_verification_code(user_id: int, db: AsyncSession) -> str:
    """Invalidate any outstanding codes for the user and mint a fresh 6-digit one."""
    existing = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user_id,
            EmailVerificationToken.used == False,  # noqa: E712
        )
    )
    for tok in existing.scalars().all():
        tok.used = True
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(EmailVerificationToken(
        user_id=user_id,
        token=code,
        expires_at=utc_now_naive() + _VERIFY_TTL,
    ))
    await db.commit()
    return code


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    # Brute-force guard: cap attempts per real client IP. Keyed on IP (not the
    # submitted username) on purpose — a per-account counter would let an attacker
    # lock a victim out by spamming failed logins for their name. 10 / 5 min is
    # well above any human's fumble rate but throttles automated guessing.
    if not check_rate(f"login-ip:{_client_ip(request)}", max_hits=10, window_seconds=300):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait a few minutes and try again.",
        )
    ident = payload.username.strip()
    # One field, two identifiers: match against username OR email (v1.24).
    result = await db.execute(
        select(User).where(
            or_(User.username == ident, func.lower(User.email) == ident.lower())
        )
    )
    user = result.scalar_one_or_none()
    # Constant-work verify: always run bcrypt (against a dummy hash when the account
    # doesn't exist) so the not-found and wrong-password paths take the same time and
    # can't be told apart to enumerate registered usernames/emails.
    password_ok = verify_password(payload.password, user.password_hash if user else _DUMMY_PW_HASH)
    if not user or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return TokenOut(access_token=create_access_token(user.id, user.token_version or 0))


@router.post("/google", response_model=TokenOut)
async def google_auth(payload: GoogleAuthIn, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Sign in / sign up with Google. The Google ID token already proves email
    ownership, so these accounts are created email_verified=True (no code)."""
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google sign-in isn't configured.")

    # Verify the ID token via Google's tokeninfo endpoint (no extra crypto deps).
    # tokeninfo only returns 200 for tokens with a valid signature and unexpired.
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": payload.credential},
            )
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't reach Google. Please try again.")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google sign-in.")
    info = r.json()
    # Critical checks: the token must be minted for OUR app and issued by Google.
    if info.get("aud") != _GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Invalid Google sign-in.")
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status_code=401, detail="Invalid Google sign-in.")
    if str(info.get("email_verified")).lower() != "true":
        raise HTTPException(status_code=403, detail="Your Google account email isn't verified.")
    email = (info.get("email") or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Google didn't share a usable email.")

    # Existing account → just log in (matched by email).
    existing = await db.execute(select(User).where(func.lower(User.email) == email))
    user = existing.scalar_one_or_none()
    if user:
        return TokenOut(access_token=create_access_token(user.id, user.token_version or 0))

    # New account. Enforce the 13+ age gate when a DOB was supplied (signup page);
    # leave it unset otherwise (is_minor treats unknown as adult — see note in PR).
    birth_year = None
    birth_date = None
    consent = "ask"
    if payload.birth_date:
        try:
            bd = date.fromisoformat(payload.birth_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Please enter a valid date of birth.")
        today = date.today()
        if bd > today or bd.year < 1900:
            raise HTTPException(status_code=400, detail="Please enter a valid date of birth.")
        age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        if age < 13:
            raise HTTPException(status_code=403, detail="You must be 13 or older to use Surge.")
        birth_year, birth_date = bd.year, payload.birth_date
        consent = "no" if age < 18 else "ask"

    # Username from the Google display name (or email local part), de-duplicated.
    base = (info.get("name") or email.split("@")[0]).strip()[:30] or "creator"
    username = base
    suffix = 0
    while (await db.execute(select(User).where(User.username == username))).scalar_one_or_none():
        suffix += 1
        username = f"{base}{suffix}"[:32]

    user = User(
        username=username,
        email=email,
        birth_year=birth_year,
        birth_date=birth_date,
        seed_consent=consent,
        password_hash=hash_password(secrets.token_urlsafe(32)),  # unusable; OAuth-only
        email_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    background_tasks.add_task(_send_welcome_email, user.email, user.username)
    return TokenOut(access_token=create_access_token(user.id, user.token_version or 0))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(require_user)):
    return user_to_out(user)


@router.post("/verify-email", response_model=UserOut)
async def verify_email(
    payload: VerifyEmailIn,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # Brute-force guard: codes are 6 digits and scoped to this user; cap guesses.
    if not check_rate(f"verify-email-ip:{_client_ip(request)}", max_hits=20, window_seconds=600):
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait a few minutes.")

    if user.email_verified:
        return user_to_out(user)

    code = payload.code.strip()
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.token == code,
            EmailVerificationToken.used == False,  # noqa: E712
        )
    )
    tok = result.scalar_one_or_none()
    if not tok or tok.expires_at < utc_now_naive():
        raise HTTPException(status_code=400, detail="Invalid or expired code. Request a new one.")

    user.email_verified = True
    tok.used = True
    await db.commit()
    await db.refresh(user)

    if user.email:
        background_tasks.add_task(_send_welcome_email, user.email, user.username)
    return user_to_out(user)


@router.post("/resend-verification")
async def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if user.email_verified or not user.email:
        return {"ok": True}
    # Per-IP + per-email caps protect the inbox and the Brevo quota.
    if not check_rate(f"verify-resend-ip:{_client_ip(request)}", max_hits=5, window_seconds=900):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a few minutes.")
    recent_cutoff = utc_now_naive() - timedelta(hours=1)
    recent_q = await db.execute(
        select(func.count()).select_from(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.created_at >= recent_cutoff,
        )
    )
    if (recent_q.scalar() or 0) >= _VERIFY_PER_EMAIL_HOUR:
        return {"ok": True}
    code = await _issue_verification_code(user.id, db)
    background_tasks.add_task(_send_verification_email, user.email, user.username, code)
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordIn, background_tasks: BackgroundTasks, request: Request, db: AsyncSession = Depends(get_db)):
    # Per-IP guard: stop a script from spraying requests to burn the Brevo quota.
    # IP-based, so it's independent of whether the email exists (no enumeration leak).
    if not check_rate(f"forgot-ip:{_client_ip(request)}", max_hits=5, window_seconds=900):
        raise HTTPException(
            status_code=429,
            detail="Too many reset requests. Please wait a few minutes and try again.",
        )

    email = payload.email.strip().lower()
    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()
    # Always return 200 — never reveal whether the email exists.
    if not user or not user.email:
        return {"ok": True}

    # Per-email cap (persistent across restarts via created_at): silently no-op
    # past the hourly limit so a victim's inbox can't be flooded. Same 200 as the
    # not-found path, so it still leaks nothing about account existence.
    recent_cutoff = utc_now_naive() - timedelta(hours=1)
    recent_q = await db.execute(
        select(func.count()).select_from(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at >= recent_cutoff,
        )
    )
    if (recent_q.scalar() or 0) >= _RESET_PER_EMAIL_HOUR:
        logger.info("Reset rate cap hit for user %s — suppressing email", user.id)
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
        expires_at=utc_now_naive() + _RESET_TTL,
    )
    db.add(reset)
    await db.commit()

    background_tasks.add_task(_send_reset_email, user.email, user.username, token)
    return {"ok": True}


async def _find_reset_token(token: str, email: str | None, db: AsyncSession):
    """Resolve a reset token. When an email is supplied the match is SCOPED to that
    account — so guessing a 6-digit code blind can't hijack some other user who
    happens to have an active token (defense in depth on top of the IP rate limit).
    Without an email (legacy clients) it falls back to a global token match. An
    email that maps to no account returns None so nothing is leaked about who exists.
    """
    conds = [PasswordResetToken.token == token]
    if email:
        u = (await db.execute(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )).scalar_one_or_none()
        if u is None:
            return None
        conds.append(PasswordResetToken.user_id == u.id)
    return (await db.execute(select(PasswordResetToken).where(*conds))).scalar_one_or_none()


@router.post("/verify-reset-code")
async def verify_reset_code(payload: VerifyResetCodeIn, request: Request, db: AsyncSession = Depends(get_db)):
    # Brute-force guard: cap guesses per real client IP. 20 / 10 min vs a 1M code
    # space inside the 1h TTL = negligible hit chance; email-scoping (below) closes
    # the residual "hit any active token" angle.
    if not check_rate(f"reset-verify-ip:{_client_ip(request)}", max_hits=20, window_seconds=600):
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait a few minutes.")

    reset = await _find_reset_token(payload.token, payload.email, db)
    if not reset or reset.used or reset.expires_at < utc_now_naive():
        raise HTTPException(status_code=400, detail="Invalid or expired code.")
    return {"valid": True}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordIn, request: Request, db: AsyncSession = Depends(get_db)):
    # Same brute-force guard as verify — this endpoint also matches the code globally.
    if not check_rate(f"reset-pw-ip:{_client_ip(request)}", max_hits=20, window_seconds=600):
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait a few minutes.")

    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    reset = await _find_reset_token(payload.token, payload.email, db)

    if not reset or reset.used or reset.expires_at < utc_now_naive():
        raise HTTPException(status_code=400, detail="Invalid or expired code. Please request a new one.")

    user_result = await db.execute(select(User).where(User.id == reset.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="User not found.")

    user.password_hash = hash_password(payload.new_password)
    # Invalidate every JWT issued before this reset — if the account was
    # compromised, the attacker's outstanding token stops working immediately.
    user.token_version = (user.token_version or 0) + 1
    reset.used = True
    await db.commit()

    return {"ok": True}


def _parse_sender(raw: str) -> tuple[str, str]:
    """Split 'Surge <foo@bar.com>' into ('Surge', 'foo@bar.com'). Falls back to the
    raw value as the address with a default display name."""
    m = re.match(r"^\s*(.*?)\s*<\s*([^>]+?)\s*>\s*$", raw)
    if m:
        return (m.group(1) or "Surge"), m.group(2)
    return "Surge", raw.strip()


async def _send_via_brevo_api(to_email: str, subject: str, html: str, plain: str) -> bool:
    """Send through Brevo's transactional HTTP API (HTTPS/443). Returns True on success."""
    name, addr = _parse_sender(_EMAIL_FROM)
    payload = {
        "sender": {"name": name, "email": addr},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html,
        "textContent": plain,
    }
    headers = {
        "api-key": _BREVO_API_KEY,
        "content-type": "application/json",
        "accept": "application/json",
    }
    last_err: str | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    "https://api.brevo.com/v3/smtp/email", json=payload, headers=headers
                )
            if r.status_code in (200, 201):
                msg_id = r.json().get("messageId") if r.content else None
                logger.info("Email sent to %s via Brevo API (attempt %d, msgId=%s)", to_email, attempt + 1, msg_id)
                return True
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            logger.warning("Brevo API attempt %d for %s: %s", attempt + 1, to_email, last_err)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            logger.warning("Brevo API attempt %d failed for %s: %s", attempt + 1, to_email, last_err)
        if attempt < 2:
            await asyncio.sleep(2 ** attempt)  # 1s, 2s
    logger.error("All Brevo API attempts failed for %s: %s", to_email, last_err)
    return False


async def _send_via_smtp(to_email: str, subject: str, html: str, plain: str) -> bool:
    """Send through Brevo SMTP. Works locally; BLOCKED on Railway (all SMTP ports)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
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
            logger.info("Email sent to %s via SMTP (attempt %d)", to_email, attempt + 1)
            return True
        except Exception as e:
            last_err = e
            logger.warning("SMTP attempt %d failed for %s: %s: %s", attempt + 1, to_email, type(e).__name__, e)
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s
    logger.error("All SMTP attempts failed for %s: %s", to_email, last_err)
    return False


async def _send_email(to_email: str, subject: str, html: str, plain: str) -> bool:
    """Dispatch an email. Prefers the Brevo HTTP API (Railway blocks SMTP); falls
    back to SMTP only when no API key is set (local dev)."""
    if _BREVO_API_KEY:
        return await _send_via_brevo_api(to_email, subject, html, plain)
    if _SMTP_USER and _SMTP_PASS:
        return await _send_via_smtp(to_email, subject, html, plain)
    logger.error(
        "EMAIL NOT CONFIGURED — message to %s NOT sent. Set BREVO_API_KEY (preferred) "
        "or SMTP_* env vars.",
        to_email,
    )
    return False


async def _send_reset_email(to_email: str, username: str, code: str) -> None:
    safe_username = _html.escape(username)
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#6d28d9">Surge — Password Reset</h2>
      <p>Hi <strong>{safe_username}</strong>,</p>
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
    await _send_email(to_email, "Reset your Surge password", html, plain)


async def _send_verification_email(to_email: str, username: str, code: str) -> None:
    safe_username = _html.escape(username)
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#6d28d9">Confirm your email</h2>
      <p>Hi <strong>{safe_username}</strong>,</p>
      <p>Welcome to Surge! Enter this code to confirm your email address:</p>
      <p style="margin:24px 0;text-align:center">
        <span style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#6d28d9">{code}</span>
      </p>
      <p style="color:#888;font-size:13px">
        This code expires in 24 hours. If you didn't create a Surge account, ignore this email.
      </p>
      <p style="color:#888;font-size:12px">— The Surge team</p>
    </div>
    """
    plain = (
        f"Hi {username},\n\n"
        f"Welcome to Surge! Your email confirmation code is: {code}\n\n"
        f"It expires in 24 hours. If you didn't create an account, ignore this email.\n\n"
        f"— The Surge team"
    )
    await _send_email(to_email, "Confirm your Surge email", html, plain)


async def _send_welcome_email(to_email: str, username: str) -> None:
    safe_username = _html.escape(username)
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#6d28d9">Welcome to Surge, {safe_username}!</h2>
      <p>You're all set. Upload your first video for an AI-assisted craft review and a clear experiment to test.</p>
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
        f"for an AI-assisted craft review and a clear experiment to test.\n\n"
        f"— The Surge team"
    )
    await _send_email(to_email, "Welcome to Surge 🎬", html, plain)
