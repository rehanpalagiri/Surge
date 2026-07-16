"""Stripe billing for CraftLint Pro ($9.99/mo).

Design rules (mirrors the rest of the codebase):
  - The signature-verified webhook is the ONLY writer of subscription state.
    The client is never trusted to say "I'm Pro".
  - Pro access is read from `users.subscription_status` via `auth.is_pro`.
  - Configured-OFF by default: if the Stripe library, secret key, or price ID is
    missing the billing routes return 503 and the rest of the app is unaffected
    (same pattern as Google sign-in). The app still boots without Stripe.
  - The Stripe SDK is synchronous; network calls run in a worker thread so they
    never block the event loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User

logger = logging.getLogger(__name__)

try:
    import stripe
except ImportError:  # pragma: no cover - library is in requirements; guard for safety
    stripe = None  # type: ignore

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
_FRONTEND_URL = os.getenv("FRONTEND_URL", "https://surge-chi-khaki.vercel.app").rstrip("/")

if stripe is not None and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def is_configured() -> bool:
    """Checkout/portal need a secret key + a price; the webhook needs the signing
    secret. Routes check the slice they require."""
    return stripe is not None and bool(STRIPE_SECRET_KEY) and bool(STRIPE_PRICE_ID)


def webhook_configured() -> bool:
    return stripe is not None and bool(STRIPE_WEBHOOK_SECRET)


def _g(obj, key, default=None):
    """Safe field read that works for BOTH a Stripe ``StripeObject`` and a plain
    dict. Stripe's object raises on ``.get()`` (attribute access is intercepted
    as a key lookup), so we never call ``.get()`` on event data — we use ``in`` +
    ``[]``, both of which the StripeObject and dict support."""
    try:
        return obj[key] if key in obj else default
    except (KeyError, TypeError):
        return default


def _ts_to_naive(ts) -> Optional[datetime]:
    """Stripe sends UNIX timestamps; store as naive UTC to match the DB columns."""
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _period_end(sub) -> Optional[datetime]:
    """current_period_end moved onto subscription items in recent API versions;
    read the top-level field first, then fall back to the first item."""
    end = _g(sub, "current_period_end")
    if not end:
        items = _g(sub, "items", {})
        data = _g(items, "data", []) or []
        if data:
            end = _g(data[0], "current_period_end")
    return _ts_to_naive(end)


# ─────────────────────────────────────────────────────────────────────────────
# Checkout + portal (called from authenticated routes)
# ─────────────────────────────────────────────────────────────────────────────

async def _ensure_customer(user: User, db: AsyncSession) -> str:
    """Return the user's Stripe customer id, creating + persisting one if needed."""
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = await asyncio.to_thread(
        stripe.Customer.create,
        email=user.email or None,
        name=user.username,
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer["id"]
    await db.commit()
    return customer["id"]


async def create_checkout_session(user: User, db: AsyncSession) -> str:
    """Create a subscription Checkout Session and return its hosted URL."""
    customer_id = await _ensure_customer(user, db)
    session = await asyncio.to_thread(
        lambda: stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=str(user.id),
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            allow_promotion_codes=True,
            success_url=f"{_FRONTEND_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{_FRONTEND_URL}/billing/cancel",
            subscription_data={"metadata": {"user_id": str(user.id)}},
        )
    )
    return session["url"]


async def create_portal_session(user: User) -> str:
    """Stripe-hosted billing portal so users can update card / cancel."""
    if not user.stripe_customer_id:
        raise ValueError("No Stripe customer on file for this user.")
    session = await asyncio.to_thread(
        lambda: stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{_FRONTEND_URL}/settings",
        )
    )
    return session["url"]


# ─────────────────────────────────────────────────────────────────────────────
# Webhook
# ─────────────────────────────────────────────────────────────────────────────

def construct_event(payload: bytes, sig_header: str):
    """Verify the Stripe signature and return the parsed event.

    Raises stripe.error.SignatureVerificationError on a bad/spoofed signature
    and ValueError on an unparseable body — the route maps both to 400 so an
    attacker can never inject a fake "you're Pro" event.
    """
    return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)


async def _user_by_customer(db: AsyncSession, customer_id: Optional[str]) -> Optional[User]:
    if not customer_id:
        return None
    return (await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )).scalar_one_or_none()


async def _user_for_event(db: AsyncSession, obj) -> Optional[User]:
    """Resolve the User from an event object: client_reference_id (checkout),
    then customer id, then subscription metadata.user_id — in that order."""
    ref = _g(obj, "client_reference_id")
    if ref and str(ref).isdigit():
        u = (await db.execute(select(User).where(User.id == int(ref)))).scalar_one_or_none()
        if u:
            return u
    u = await _user_by_customer(db, _g(obj, "customer"))
    if u:
        return u
    meta_uid = _g(_g(obj, "metadata", {}) or {}, "user_id")
    if meta_uid and str(meta_uid).isdigit():
        return (await db.execute(select(User).where(User.id == int(meta_uid)))).scalar_one_or_none()
    return None


def _apply_subscription(user: User, sub) -> None:
    user.stripe_subscription_id = _g(sub, "id") or user.stripe_subscription_id
    user.subscription_status = _g(sub, "status")
    user.subscription_current_period_end = _period_end(sub)
    cust = _g(sub, "customer")
    if cust and not user.stripe_customer_id:
        user.stripe_customer_id = cust


async def apply_event(event, db: AsyncSession) -> str:
    """Idempotently apply a verified Stripe event to the user's billing state.

    Returns a short label of what happened (handy for the webhook response and
    tests). Unhandled event types are a no-op ("ignored").
    """
    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        user = await _user_for_event(db, obj)
        if user is None:
            logger.warning("checkout.session.completed: no user for session %s", _g(obj, "id"))
            return "no_user"
        customer = _g(obj, "customer")
        if customer and not user.stripe_customer_id:
            user.stripe_customer_id = customer
        sub_id = _g(obj, "subscription")
        if sub_id:
            sub = await asyncio.to_thread(stripe.Subscription.retrieve, sub_id)
            _apply_subscription(user, sub)
        await db.commit()
        logger.info("Stripe: user %s upgraded via checkout (status=%s)", user.id, user.subscription_status)
        return "upgraded"

    if etype in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"):
        user = await _user_for_event(db, obj)
        if user is None:
            logger.warning("%s: no user for customer %s", etype, _g(obj, "customer"))
            return "no_user"
        _apply_subscription(user, obj)
        await db.commit()
        logger.info("Stripe: user %s subscription %s (status=%s)", user.id, etype.split(".")[-1], user.subscription_status)
        return "subscription_synced"

    if etype == "invoice.payment_failed":
        user = await _user_by_customer(db, _g(obj, "customer"))
        if user is None:
            return "no_user"
        # Keep access during Stripe's retry window but flag the account. Stripe
        # emits subscription.deleted once it finally gives up, which ends access.
        user.subscription_status = "past_due"
        await db.commit()
        logger.info("Stripe: user %s payment failed — flagged past_due", user.id)
        return "payment_failed"

    return "ignored"
