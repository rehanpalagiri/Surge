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


def _event(etype: str, obj: dict) -> bytes:
    # Real Stripe events carry a top-level "object": "event"; the v15 SDK's
    # construct_event reads it, so include it for a faithful round-trip.
    return json.dumps(
        {"id": "evt_1", "object": "event", "type": etype, "data": {"object": obj}}
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
        billing.STRIPE_WEBHOOK_SECRET = WHSEC
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
        app.dependency_overrides.pop(get_db, None)
        await self.engine.dispose()

    async def _status(self) -> str | None:
        async with self.Session() as db:
            u = (await db.execute(select(User).where(User.id == self.user_id))).scalar_one()
            return u.subscription_status

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
        future = int(time.time()) + 30 * 24 * 3600
        body = _event("customer.subscription.updated",
                      {"customer": "cus_123", "id": "sub_1", "status": "active",
                       "current_period_end": future})
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
        body = _event("customer.subscription.deleted",
                      {"customer": "cus_123", "id": "sub_1", "status": "canceled"})
        r = await self.client.post("/api/billing/webhook", content=body,
                                   headers={"stripe-signature": _sign(body), "content-type": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(await self._status(), "canceled")

    async def test_payment_failed_flags_past_due(self):
        body = _event("invoice.payment_failed", {"customer": "cus_123", "id": "in_1"})
        with patch("routers.auth._send_email") as send:  # don't attempt a real email
            send.return_value = True
            r = await self.client.post("/api/billing/webhook", content=body,
                                       headers={"stripe-signature": _sign(body), "content-type": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result"], "payment_failed")
        self.assertEqual(await self._status(), "past_due")

    async def test_checkout_completed_retrieves_and_applies_subscription(self):
        future = int(time.time()) + 30 * 24 * 3600
        body = _event("checkout.session.completed",
                      {"id": "cs_1", "client_reference_id": str(self.user_id),
                       "customer": "cus_123", "subscription": "sub_1"})
        fake_sub = {"id": "sub_1", "status": "active", "current_period_end": future}
        with patch("services.stripe_billing.stripe.Subscription.retrieve", return_value=fake_sub):
            r = await self.client.post("/api/billing/webhook", content=body,
                                       headers={"stripe-signature": _sign(body), "content-type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["result"], "upgraded")
        self.assertEqual(await self._status(), "active")

    # ── Authed endpoints ────────────────────────────────────────────────────
    async def test_status_reflects_subscription(self):
        auth = {"Authorization": f"Bearer {self.token}"}
        r = await self.client.get("/api/billing/status", headers=auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["plan"], "free")
        self.assertFalse(r.json()["is_pro"])

        async with self.Session() as db:
            u = (await db.execute(select(User).where(User.id == self.user_id))).scalar_one()
            u.subscription_status = "active"
            await db.commit()
        r = await self.client.get("/api/billing/status", headers=auth)
        self.assertEqual(r.json()["plan"], "pro")
        self.assertTrue(r.json()["is_pro"])

    async def test_status_requires_auth(self):
        self.assertEqual((await self.client.get("/api/billing/status")).status_code, 401)

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
