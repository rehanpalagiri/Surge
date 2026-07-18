"""Stripe-hosted recurring billing for CraftLint Pro ($9.99 USD/month).

Security and reliability invariants:
  - Only a signature-verified, price-validated webhook writes paid access.
  - Stripe webhook event ids are stored before commit for at-least-once safety.
  - Every subscription event reconciles the customer's current Stripe state, so
    delayed/out-of-order events cannot overwrite a newer subscription state.
  - Checkout rejects minors and duplicate/pending target-plan subscriptions.
  - Stripe's synchronous SDK always runs off the asyncio event loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import StripeWebhookEvent, User

logger = logging.getLogger(__name__)

try:
    import stripe
except ImportError:  # pragma: no cover
    stripe = None  # type: ignore

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
_FRONTEND_URL = os.getenv(
    "FRONTEND_URL", "https://surge-chi-khaki.vercel.app"
).rstrip("/")

if stripe is not None and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

_TERMINAL_STATUSES = frozenset({"canceled", "incomplete_expired"})
_STATUS_PRIORITY = {
    "active": 7,
    "trialing": 6,
    "past_due": 5,
    "incomplete": 4,
    "paused": 3,
    "unpaid": 2,
    "canceled": 1,
    "incomplete_expired": 0,
}


class ExistingSubscriptionError(ValueError):
    """The customer already has this plan in a non-terminal state."""


class CheckoutSessionAccessError(ValueError):
    """The requested Checkout Session does not belong to the signed-in user."""


def is_configured() -> bool:
    return stripe is not None and bool(STRIPE_SECRET_KEY) and bool(STRIPE_PRICE_ID)


def webhook_configured() -> bool:
    return stripe is not None and bool(STRIPE_WEBHOOK_SECRET)


def _g(obj, key, default=None):
    """Read both StripeObjects and dicts without StripeObject.get()."""
    try:
        return obj[key] if key in obj else default
    except (KeyError, TypeError):
        return default


def _ts_to_naive(ts) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _period_end(sub) -> Optional[datetime]:
    end = _g(sub, "current_period_end")
    if not end:
        data = _g(_g(sub, "items", {}) or {}, "data", []) or []
        if data:
            end = _g(data[0], "current_period_end")
    return _ts_to_naive(end)


def _subscription_has_target_price(sub) -> bool:
    items = _g(_g(sub, "items", {}) or {}, "data", []) or []
    for item in items:
        price = _g(item, "price", {}) or {}
        price_id = price if isinstance(price, str) else _g(price, "id")
        if price_id == STRIPE_PRICE_ID:
            return True
    return False


def _invoice_subscription_id(invoice) -> Optional[str]:
    """Support both legacy invoice.subscription and the newer parent shape."""
    direct = _g(invoice, "subscription")
    if direct:
        return str(direct)
    parent = _g(invoice, "parent", {}) or {}
    details = _g(parent, "subscription_details", {}) or {}
    nested = _g(details, "subscription")
    return str(nested) if nested else None


async def _list_target_subscriptions(customer_id: str) -> list:
    collection = await asyncio.to_thread(
        lambda: stripe.Subscription.list(
            customer=customer_id,
            status="all",
            limit=100,
        )
    )
    return [
        sub
        for sub in (_g(collection, "data", []) or [])
        if _subscription_has_target_price(sub)
    ]


def _choose_current_subscription(subscriptions: list):
    if not subscriptions:
        return None

    def sort_key(sub):
        status = str(_g(sub, "status", "") or "")
        return (
            _STATUS_PRIORITY.get(status, -1),
            int(_g(sub, "created", 0) or 0),
            int(_g(sub, "current_period_end", 0) or 0),
        )

    return max(subscriptions, key=sort_key)


def _apply_subscription(user: User, sub) -> None:
    user.stripe_subscription_id = _g(sub, "id") or user.stripe_subscription_id
    user.subscription_status = _g(sub, "status")
    user.subscription_current_period_end = _period_end(sub)
    user.subscription_cancel_at_period_end = bool(
        _g(sub, "cancel_at_period_end", False)
    )
    customer = _g(sub, "customer")
    if customer:
        user.stripe_customer_id = customer


async def _reconcile_customer(user: User, customer_id: str):
    """Apply the best current target-plan subscription from Stripe.

    Listing current state instead of trusting an event's historical snapshot
    makes delivery order irrelevant and handles an accidental second
    subscription without letting an older cancellation revoke a newer plan.
    """
    subscriptions = await _list_target_subscriptions(customer_id)
    current = _choose_current_subscription(subscriptions)
    if current is not None:
        _apply_subscription(user, current)
    return current


# ── Checkout + portal ────────────────────────────────────────────────────────

async def _ensure_customer(user: User, db: AsyncSession) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = await asyncio.to_thread(
        lambda: stripe.Customer.create(
            email=user.email or None,
            name=user.username,
            metadata={"user_id": str(user.id)},
            idempotency_key=f"craftlint-customer-{user.id}",
        )
    )
    user.stripe_customer_id = customer["id"]
    await db.commit()
    return customer["id"]


async def create_checkout_session(user: User, db: AsyncSession) -> str:
    customer_id = await _ensure_customer(user, db)
    existing = await _list_target_subscriptions(customer_id)
    if any(
        str(_g(sub, "status", "") or "") not in _TERMINAL_STATUSES
        for sub in existing
    ):
        raise ExistingSubscriptionError(
            "A pending or existing CraftLint Pro subscription already exists."
        )

    # Collapse double-clicks/retries within five minutes into the same session.
    bucket = int(time.time() // 300)
    session = await asyncio.to_thread(
        lambda: stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=str(user.id),
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            allow_promotion_codes=True,
            success_url=(
                f"{_FRONTEND_URL}/billing/success"
                "?session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=f"{_FRONTEND_URL}/billing/cancel",
            subscription_data={"metadata": {"user_id": str(user.id)}},
            metadata={"user_id": str(user.id), "plan": "craftlint_pro"},
            idempotency_key=f"craftlint-checkout-{user.id}-{bucket}",
        )
    )
    return session["url"]


async def checkout_session_status(user: User, session_id: str) -> dict:
    if not session_id.startswith("cs_"):
        raise CheckoutSessionAccessError("Invalid Checkout Session.")
    session = await asyncio.to_thread(
        stripe.checkout.Session.retrieve, session_id
    )
    customer = _g(session, "customer")
    reference = str(_g(session, "client_reference_id", "") or "")
    belongs_to_user = (
        (user.stripe_customer_id and customer == user.stripe_customer_id)
        or reference == str(user.id)
    )
    if not belongs_to_user:
        raise CheckoutSessionAccessError(
            "This Checkout Session does not belong to your account."
        )
    return {
        "status": _g(session, "status"),
        "payment_status": _g(session, "payment_status"),
    }


async def create_portal_session(user: User) -> str:
    if not user.stripe_customer_id:
        raise ValueError("No Stripe customer on file for this user.")
    session = await asyncio.to_thread(
        lambda: stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{_FRONTEND_URL}/settings",
        )
    )
    return session["url"]


async def cancel_for_account_deletion(user: User) -> None:
    """Stop future charges before permanently deleting a paid account.

    Account deletion ends service immediately, so unlike ordinary portal
    cancellation this cancels the Stripe subscription immediately. A Stripe API
    failure must block deletion rather than orphan a still-charging subscription.
    """
    if (
        not user.stripe_subscription_id
        or str(user.subscription_status or "") in _TERMINAL_STATUSES
    ):
        return
    await asyncio.to_thread(
        stripe.Subscription.cancel, user.stripe_subscription_id
    )


# ── Webhook ─────────────────────────────────────────────────────────────────

def construct_event(payload: bytes, sig_header: str):
    return stripe.Webhook.construct_event(
        payload, sig_header, STRIPE_WEBHOOK_SECRET
    )


async def _user_by_customer(
    db: AsyncSession, customer_id: Optional[str]
) -> Optional[User]:
    if not customer_id:
        return None
    return (
        await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
    ).scalar_one_or_none()


async def _user_for_event(db: AsyncSession, obj) -> Optional[User]:
    reference = _g(obj, "client_reference_id")
    if reference and str(reference).isdigit():
        user = (
            await db.execute(
                select(User).where(User.id == int(reference))
            )
        ).scalar_one_or_none()
        if user:
            return user
    user = await _user_by_customer(db, _g(obj, "customer"))
    if user:
        return user
    metadata_user_id = _g(_g(obj, "metadata", {}) or {}, "user_id")
    if metadata_user_id and str(metadata_user_id).isdigit():
        return (
            await db.execute(
                select(User).where(User.id == int(metadata_user_id))
            )
        ).scalar_one_or_none()
    return None


async def _begin_event(event, db: AsyncSession):
    event_id = str(_g(event, "id", "") or "")
    if not event_id:
        return None, False
    if await db.get(StripeWebhookEvent, event_id):
        return None, True
    record = StripeWebhookEvent(
        id=event_id,
        event_type=str(_g(event, "type", "unknown") or "unknown"),
        event_created=_g(event, "created"),
    )
    db.add(record)
    return record, False


async def _finish_event(
    db: AsyncSession, record: Optional[StripeWebhookEvent], result: str
) -> str:
    if record is not None:
        record.result = result
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent delivery inserted the same event first. Rolling back also
        # rolls back our duplicate state write, keeping the transaction atomic.
        await db.rollback()
        return "duplicate"
    return result


async def _target_invoice_subscription(invoice):
    subscription_id = _invoice_subscription_id(invoice)
    if not subscription_id:
        return None
    sub = await asyncio.to_thread(
        stripe.Subscription.retrieve, subscription_id
    )
    return sub if _subscription_has_target_price(sub) else None


async def apply_event(event, db: AsyncSession) -> str:
    """Atomically and idempotently apply one verified Stripe event."""
    record, duplicate = await _begin_event(event, db)
    if duplicate:
        return "duplicate"

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
    }:
        user = await _user_for_event(db, obj)
        if user is None:
            logger.warning(
                "checkout.session.completed: no user for session %s",
                _g(obj, "id"),
            )
            return await _finish_event(db, record, "no_user")
        customer = _g(obj, "customer")
        if not customer:
            return await _finish_event(db, record, "ignored")
        user.stripe_customer_id = customer

        if event_type == "checkout.session.async_payment_failed":
            action_id = f"checkout:{_g(obj, 'id', '')}"
            repeated = user.stripe_last_payment_action_id == action_id
            user.stripe_last_payment_action_id = action_id
            result = (
                "async_payment_failed_repeat"
                if repeated
                else "async_payment_failed"
            )
            return await _finish_event(db, record, result)

        # A completed Checkout with an unpaid delayed method is not fulfillment.
        # Wait for checkout.session.async_payment_succeeded.
        if (
            event_type == "checkout.session.completed"
            and _g(obj, "payment_status") == "unpaid"
        ):
            return await _finish_event(db, record, "payment_pending")

        current = await _reconcile_customer(user, customer)
        result = "upgraded" if current is not None else "ignored"
        return await _finish_event(db, record, result)

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.resumed",
    }:
        if not _subscription_has_target_price(obj):
            return await _finish_event(db, record, "ignored")
        user = await _user_for_event(db, obj)
        if user is None:
            return await _finish_event(db, record, "no_user")
        customer = _g(obj, "customer")
        if not customer:
            return await _finish_event(db, record, "ignored")
        current = await _reconcile_customer(user, customer)
        result = "subscription_synced" if current is not None else "ignored"
        return await _finish_event(db, record, result)

    if event_type in {
        "invoice.payment_failed",
        "invoice.payment_action_required",
        "invoice.paid",
    }:
        target_sub = await _target_invoice_subscription(obj)
        if target_sub is None:
            return await _finish_event(db, record, "ignored")
        customer = _g(obj, "customer") or _g(target_sub, "customer")
        user = await _user_by_customer(db, customer)
        if user is None:
            return await _finish_event(db, record, "no_user")
        await _reconcile_customer(user, customer)
        invoice_id = str(_g(obj, "id", "") or "")
        action_id = f"invoice:{invoice_id}"
        if event_type == "invoice.paid":
            if user.stripe_last_payment_action_id == action_id:
                user.stripe_last_payment_action_id = None
            result = "payment_recovered"
        else:
            repeated = user.stripe_last_payment_action_id == action_id
            user.stripe_last_payment_action_id = action_id
            base = {
                "invoice.payment_failed": "payment_failed",
                "invoice.payment_action_required": "payment_action_required",
            }[event_type]
            result = f"{base}_repeat" if repeated else base
        return await _finish_event(db, record, result)

    return await _finish_event(db, record, "ignored")
