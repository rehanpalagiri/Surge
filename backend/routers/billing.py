"""CraftLint Pro billing routes (Stripe).

- POST /api/billing/checkout  (auth) → hosted Checkout URL to start a subscription
- POST /api/billing/portal    (auth) → Stripe billing-portal URL (manage / cancel)
- GET  /api/billing/status    (auth) → this user's plan + subscription state
- POST /api/billing/webhook   (no auth; Stripe-signed) → applies subscription events

Everything that mutates Pro state flows through the SIGNATURE-VERIFIED webhook.
The authed routes only create Stripe sessions; they never set Pro status.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import is_comp, is_pro, require_user
from database import get_db
from models import User
from services import stripe_billing as billing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

PRICE_DISPLAY = "$9.99/mo"


@router.get("/status")
async def billing_status(user: User = Depends(require_user)):
    """Plan + subscription state for the current user (drives the UI)."""
    comp = is_comp(user)
    return {
        "plan": "pro" if is_pro(user) else "free",
        "is_pro": is_pro(user),
        "comp": comp,  # complimentary Pro (operator grant) — no Stripe to manage
        "subscription_status": user.subscription_status,
        "current_period_end": user.subscription_current_period_end,
        "has_customer": bool(user.stripe_customer_id),
        "price": PRICE_DISPLAY,
        # Comp users see the Pro UI even before Stripe is wired up.
        "configured": billing.is_configured() or comp,
    }


@router.post("/checkout")
async def create_checkout(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a CraftLint Pro subscription. Returns a Stripe hosted-checkout URL."""
    if not billing.is_configured():
        raise HTTPException(status_code=503, detail="Billing isn't configured yet.")
    if is_pro(user):
        raise HTTPException(status_code=409, detail="You're already on CraftLint Pro.")
    try:
        url = await billing.create_checkout_session(user, db)
    except Exception as exc:  # Stripe / network error — don't leak internals
        logger.error("Checkout session creation failed for user %s: %r", user.id, exc)
        raise HTTPException(status_code=502, detail="Couldn't start checkout. Please try again.")
    return {"url": url}


@router.post("/portal")
async def create_portal(user: User = Depends(require_user)):
    """Open the Stripe billing portal to manage or cancel the subscription."""
    if not billing.is_configured():
        raise HTTPException(status_code=503, detail="Billing isn't configured yet.")
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account yet — start a subscription first.")
    try:
        url = await billing.create_portal_session(user)
    except Exception as exc:
        logger.error("Portal session creation failed for user %s: %r", user.id, exc)
        raise HTTPException(status_code=502, detail="Couldn't open the billing portal. Please try again.")
    return {"url": url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Stripe → us. Verifies the signature on the RAW body before doing anything."""
    if not billing.webhook_configured():
        raise HTTPException(status_code=503, detail="Webhook not configured.")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = billing.construct_event(payload, sig)
    except Exception as exc:
        # Bad/missing/forged signature or unparseable body → reject. This is the
        # gate that stops anyone from POSTing a fake "you're Pro" event.
        logger.warning("Stripe webhook rejected: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Invalid signature.")

    try:
        result = await billing.apply_event(event, db)
    except Exception as exc:
        # Return 500 so Stripe RETRIES (its events are at-least-once). Never 200 a
        # failed apply — that would silently drop a real upgrade/downgrade.
        # (event is a StripeObject — use bracket access, never .get().)
        etype = event["type"] if "type" in event else "?"
        logger.error("Stripe webhook apply failed for %s: %r", etype, exc)
        raise HTTPException(status_code=500, detail="Webhook processing error.")

    if result == "payment_failed":
        cust = billing._g(event["data"]["object"], "customer")
        user = await billing._user_by_customer(db, cust)
        if user and user.email:
            background_tasks.add_task(_send_payment_failed_email, user.email, user.username)

    return {"received": True, "result": result}


async def _send_payment_failed_email(to_email: str, username: str) -> None:
    """Notify a user their CraftLint Pro payment failed (uses the shared sender)."""
    from routers.auth import _send_email, _FRONTEND_URL
    import html as _html
    safe = _html.escape(username)
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#6d28d9">Your CraftLint Pro payment didn't go through</h2>
      <p>Hi <strong>{safe}</strong>,</p>
      <p>We couldn't process your latest CraftLint Pro payment. Your Pro access stays
         active while we retry, but please update your card to avoid losing it.</p>
      <p style="margin:24px 0">
        <a href="{_FRONTEND_URL}/settings"
           style="background:#6d28d9;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">
          Update payment method →
        </a>
      </p>
      <p style="color:#888;font-size:12px">— The CraftLint team</p>
    </div>
    """
    plain = (
        f"Hi {username},\n\n"
        f"We couldn't process your latest CraftLint Pro payment. Your Pro access stays "
        f"active while we retry — update your card at {_FRONTEND_URL}/settings to keep it.\n\n"
        f"— The CraftLint team"
    )
    await _send_email(to_email, "Action needed: your CraftLint Pro payment failed", html, plain)
