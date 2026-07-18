"""Stripe billing tests.

Covers the security-critical path (webhook signature verification — the only
thing standing between a stranger and a forged "you're Pro" event) plus the full
subscription lifecycle and the authed endpoints. Signatures are generated the
same way Stripe does, so the real construct_event() verifier runs.
"""
import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import services.stripe_billing as billing
from auth import create_access_token
from database import get_db
from main import app
from models import Base, User

WHSEC = "whsec_test_secret_value"


def _sign(payload: bytes, secret: str = WHSEC, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    signed = f"{ts}.{payload.decode()}".encode()
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _event(etype: str, obj: dict, event_id: str = "evt_1") -> bytes:
    # Real Stripe events carry a top-level "object": "event"; the v15 SDK's
    # construct_event reads it, so include it for a faithful round-trip.
    return json.dumps(
        {"id": event_id, "object": "event", "type": etype, "data": {"object": obj}}
    ).encode()


class BillingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        async def _override_get_db():
            async with self.Session() as s:
                yield s

        app.dependency_overrides[get_db] = _override_get_db
        # Pretend the webhook secret is configured for the whole test.
        self._orig_secret = billing.STRIPE_WEBHOOK_SECRET
        self._orig_price = billing.STRIPE_PRICE_ID
        billing.STRIPE_WEBHOOK_SECRET = WHSEC
        billing.STRIPE_PRICE_ID = "price_craftlint_test"
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

        async with self.Session() as db:
            u = User(username="payer", email="payer@example.com", password_hash="x",
                     stripe_customer_id="cus_123")
            db.add(u)
            await db.commit()
            self.user_id = u.id
            self.token = create_access_token(u.id)

    async def asyncTearDown(self):
        await self.client.aclose()
        billing.STRIPE_WEBHOOK_SECRET = self._orig_secret
        billing.STRIPE_PRICE_ID = self._orig_price
        app.dependency_overrides.pop(get_db, None)
        await self.engine.dispose()

    async def _status(self) -> str | None:
        async with self.Session() as db:
            u = (await db.execute(select(User).where(User.id == self.user_id))).scalar_one()
            return u.subscription_status

    def _sub(self, status: str = "active", **overrides) -> dict:
        future = int(time.time()) + 30 * 24 * 3600
        sub = {
            "id": "sub_1",
            "customer": "cus_123",
            "status": status,
            "created": int(time.time()),
            "current_period_end": future,
            "cancel_at_period_end": False,
            "items": {
                "data": [{
                    "price": {"id": billing.STRIPE_PRICE_ID},
                    "current_period_end": future,
                }]
            },
        }
        sub.update(overrides)
        return sub

    # ── Signature verification (the security gate) ──────────────────────────
    async def test_forged_signature_is_rejected_and_changes_nothing(self):
        body = _event("customer.subscription.updated",
                      {"customer": "cus_123", "id": "sub_1", "status": "active"})
        r = await self.client.post(
            "/api/billing/webhook", content=body,
            headers={"stripe-signature": "t=1,v1=deadbeef", "content-type": "application/json"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(await self._status())  # not upgraded by a forged event

    async def test_missing_signature_rejected(self):
        body = _event("customer.subscription.updated", {"customer": "cus_123", "status": "active"})
        r = await self.client.post("/api/billing/webhook", content=body,
                                   headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 400)

    # ── Lifecycle ───────────────────────────────────────────────────────────
    async def test_valid_subscription_updated_upgrades_user(self):
        sub = self._sub()
        body = _event("customer.subscription.updated", sub)
        with patch("services.stripe_billing.stripe.Subscription.list",
                   return_value={"data": [sub]}):
            r = await self.client.post("/api/billing/webhook", content=body,
                                       headers={"stripe-signature": _sign(body), "content-type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["result"], "subscription_synced")
        self.assertEqual(await self._status(), "active")

    async def test_subscription_deleted_downgrades_user(self):
        # Start active, then delete.
        async with self.Session() as db:
            u = (await db.execute(select(User).where(User.id == self.user_id))).scalar_one()
            u.subscription_status = "active"
            await db.commit()
        sub = self._sub("canceled")
        body = _event("customer.subscription.deleted", sub)
        with patch("services.stripe_billing.stripe.Subscription.list",
                   return_value={"data": [sub]}):
            r = await self.client.post("/api/billing/webhook", content=body,
                                       headers={"stripe-signature": _sign(body), "content-type": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(await self._status(), "canceled")

    async def test_payment_failed_flags_past_due(self):
        sub = self._sub("past_due")
        body = _event("invoice.payment_failed",
                      {"customer": "cus_123", "id": "in_1", "subscription": "sub_1"})
        with patch("routers.auth._send_email") as send, \
             patch("services.stripe_billing.stripe.Subscription.retrieve",
                   return_value=sub), \
             patch("services.stripe_billing.stripe.Subscription.list",
                   return_value={"data": [sub]}):
            send.return_value = True
            r = await self.client.post("/api/billing/webhook", content=body,
                                       headers={"stripe-signature": _sign(body), "content-type": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result"], "payment_failed")
        self.assertEqual(await self._status(), "past_due")

    async def test_retries_for_same_invoice_send_one_action_email(self):
        sub = self._sub("past_due")
        invoice = {
            "customer": "cus_123",
            "id": "in_same",
            "subscription": "sub_1",
        }
        first_body = _event("invoice.payment_failed", invoice, "evt_fail_1")
        retry_body = _event("invoice.payment_failed", invoice, "evt_fail_2")
        with patch("routers.auth._send_email") as send, \
             patch("services.stripe_billing.stripe.Subscription.retrieve",
                   return_value=sub), \
             patch("services.stripe_billing.stripe.Subscription.list",
                   return_value={"data": [sub]}):
            first = await self.client.post(
                "/api/billing/webhook",
                content=first_body,
                headers={
                    "stripe-signature": _sign(first_body),
                    "content-type": "application/json",
                },
            )
            retry = await self.client.post(
                "/api/billing/webhook",
                content=retry_body,
                headers={
                    "stripe-signature": _sign(retry_body),
                    "content-type": "application/json",
                },
            )
        self.assertEqual(first.json()["result"], "payment_failed")
        self.assertEqual(retry.json()["result"], "payment_failed_repeat")
        self.assertEqual(send.await_count, 1)

    async def test_checkout_completed_retrieves_and_applies_subscription(self):
        body = _event("checkout.session.completed",
                      {"id": "cs_1", "client_reference_id": str(self.user_id),
                       "customer": "cus_123", "subscription": "sub_1"})
        fake_sub = self._sub()
        with patch("services.stripe_billing.stripe.Subscription.list",
                   return_value={"data": [fake_sub]}):
            r = await self.client.post("/api/billing/webhook", content=body,
                                       headers={"stripe-signature": _sign(body), "content-type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["result"], "upgraded")
        self.assertEqual(await self._status(), "active")

    async def test_delayed_checkout_waits_for_async_success(self):
        pending = {
            "id": "cs_delayed",
            "client_reference_id": str(self.user_id),
            "customer": "cus_123",
            "subscription": "sub_1",
            "payment_status": "unpaid",
        }
        completed_body = _event(
            "checkout.session.completed", pending, "evt_pending"
        )
        completed = await self.client.post(
            "/api/billing/webhook",
            content=completed_body,
            headers={
                "stripe-signature": _sign(completed_body),
                "content-type": "application/json",
            },
        )
        self.assertEqual(completed.json()["result"], "payment_pending")
        self.assertIsNone(await self._status())

        paid = {**pending, "payment_status": "paid"}
        paid_body = _event(
            "checkout.session.async_payment_succeeded", paid, "evt_async_paid"
        )
        sub = self._sub()
        with patch("services.stripe_billing.stripe.Subscription.list",
                   return_value={"data": [sub]}):
            succeeded = await self.client.post(
                "/api/billing/webhook",
                content=paid_body,
                headers={
                    "stripe-signature": _sign(paid_body),
                    "content-type": "application/json",
                },
            )
        self.assertEqual(succeeded.json()["result"], "upgraded")
        self.assertEqual(await self._status(), "active")

    async def test_duplicate_event_is_applied_once(self):
        sub = self._sub()
        body = _event("customer.subscription.updated", sub)
        headers = {
            "stripe-signature": _sign(body),
            "content-type": "application/json",
        }
        with patch("services.stripe_billing.stripe.Subscription.list",
                   return_value={"data": [sub]}) as list_subs:
            first = await self.client.post(
                "/api/billing/webhook", content=body, headers=headers
            )
            second = await self.client.post(
                "/api/billing/webhook", content=body, headers=headers
            )
        self.assertEqual(first.json()["result"], "subscription_synced")
        self.assertEqual(second.json()["result"], "duplicate")
        self.assertEqual(list_subs.call_count, 1)

    async def test_unrelated_subscription_price_is_ignored(self):
        other = self._sub(items={"data": [{"price": {"id": "price_other"}}]})
        body = _event("customer.subscription.updated", other)
        r = await self.client.post(
            "/api/billing/webhook",
            content=body,
            headers={
                "stripe-signature": _sign(body),
                "content-type": "application/json",
            },
        )
        self.assertEqual(r.json()["result"], "ignored")
        self.assertIsNone(await self._status())

    # ── Authed endpoints ────────────────────────────────────────────────────
    async def test_status_reflects_subscription(self):
        auth = {"Authorization": f"Bearer {self.token}"}
        r = await self.client.get("/api/billing/status", headers=auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["plan"], "free")
        self.assertFalse(r.json()["is_pro"])
        self.assertTrue(r.json()["eligible_for_paid"])

        async with self.Session() as db:
            u = (await db.execute(select(User).where(User.id == self.user_id))).scalar_one()
            u.subscription_status = "active"
            await db.commit()
        r = await self.client.get("/api/billing/status", headers=auth)
        self.assertEqual(r.json()["plan"], "pro")
        self.assertTrue(r.json()["is_pro"])

    async def test_status_requires_auth(self):
        self.assertEqual((await self.client.get("/api/billing/status")).status_code, 401)

    async def test_minor_cannot_start_checkout(self):
        async with self.Session() as db:
            u = (await db.execute(select(User).where(User.id == self.user_id))).scalar_one()
            u.birth_date = f"{time.gmtime().tm_year - 16}-01-01"
            await db.commit()
        auth = {"Authorization": f"Bearer {self.token}"}
        with patch.object(billing, "STRIPE_SECRET_KEY", "sk_test_configured"), \
             patch.object(billing, "STRIPE_PRICE_ID", "price_test"):
            status = await self.client.get("/api/billing/status", headers=auth)
            checkout = await self.client.post("/api/billing/checkout", headers=auth)
        self.assertFalse(status.json()["eligible_for_paid"])
        self.assertEqual(checkout.status_code, 403)

    async def test_checkout_session_must_belong_to_user(self):
        auth = {"Authorization": f"Bearer {self.token}"}
        fake = {
            "id": "cs_test_other",
            "customer": "cus_other",
            "client_reference_id": "999",
            "status": "complete",
            "payment_status": "paid",
        }
        with patch.object(billing, "STRIPE_SECRET_KEY", "sk_test_configured"), \
             patch("services.stripe_billing.stripe.checkout.Session.retrieve",
                   return_value=fake):
            r = await self.client.get(
                "/api/billing/checkout-session/cs_test_other", headers=auth
            )
        self.assertEqual(r.status_code, 404)

    async def test_account_deletion_cancellation_uses_stripe(self):
        async with self.Session() as db:
            u = (await db.execute(select(User).where(User.id == self.user_id))).scalar_one()
            u.stripe_subscription_id = "sub_1"
            u.subscription_status = "active"
            await db.commit()
            with patch(
                "services.stripe_billing.stripe.Subscription.cancel"
            ) as cancel:
                await billing.cancel_for_account_deletion(u)
            cancel.assert_called_once_with("sub_1")

    async def test_checkout_503_when_unconfigured(self):
        # Force the unconfigured state rather than assuming the ambient env is
        # empty: a local .env with real STRIPE_SECRET_KEY/PRICE_ID would flip
        # is_configured() to True and make this exercise the wrong path.
        auth = {"Authorization": f"Bearer {self.token}"}
        with patch.object(billing, "STRIPE_SECRET_KEY", ""), \
             patch.object(billing, "STRIPE_PRICE_ID", ""):
            r = await self.client.post("/api/billing/checkout", headers=auth)
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
