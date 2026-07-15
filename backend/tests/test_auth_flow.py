"""End-to-end tests for the email-verification + Google auth flow.

Drives the real FastAPI app through httpx's ASGI transport with an in-memory
SQLite DB (StaticPool so every request shares one connection). Email sending is
stubbed so no real mail goes out and the tests stay hermetic and offline.
"""
import unittest
import uuid
from datetime import datetime, timedelta
from services.clock import utc_now_naive

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import get_db
from main import app
from models import Base, EmailVerificationToken, User
from routers import auth as auth_router


class AuthFlowTest(unittest.IsolatedAsyncioTestCase):
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

        # Stub the email transport so background tasks never hit Brevo/SMTP.
        self.sent: list[tuple] = []
        self._orig_send = auth_router._send_email

        async def _fake_send(to_email, subject, html, plain):
            self.sent.append((to_email, subject))
            return True

        auth_router._send_email = _fake_send
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        auth_router._send_email = self._orig_send
        app.dependency_overrides.pop(get_db, None)
        await self.engine.dispose()

    async def _signup(self, email="creator@example.com", username="creator"):
        # Unique per-call IP: signup is now IP-throttled (5/900s) and the throttle
        # state is process-global, so a shared IP would bleed across tests.
        return await self.client.post("/api/auth/signup", json={
            "email": email, "username": username,
            "password": "supersecret1", "birth_date": "1995-06-15",
        }, headers={"X-Forwarded-For": f"signup-{uuid.uuid4()}"})

    async def _latest_code(self) -> str:
        async with self.Session() as s:
            return (await s.execute(
                select(EmailVerificationToken.token).order_by(EmailVerificationToken.id.desc())
            )).scalars().first()

    async def test_signup_creates_unverified_user_token_and_code(self):
        r = await self._signup()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["access_token"])
        async with self.Session() as s:
            user = (await s.execute(
                select(User).where(User.email == "creator@example.com")
            )).scalar_one()
            self.assertFalse(user.email_verified)  # must start unverified
        self.assertEqual(len(await self._latest_code()), 6)
        # A verification email was dispatched (stubbed).
        self.assertTrue(any("Confirm" in subj for _, subj in self.sent))

    async def test_verify_email_happy_path(self):
        token = (await self._signup()).json()["access_token"]
        code = await self._latest_code()
        v = await self.client.post(
            "/api/auth/verify-email", json={"code": code},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(v.status_code, 200, v.text)
        self.assertTrue(v.json()["email_verified"])
        # Welcome email follows verification.
        self.assertTrue(any("Welcome" in subj for _, subj in self.sent))

    async def test_verify_email_wrong_code_rejected(self):
        token = (await self._signup()).json()["access_token"]
        v = await self.client.post(
            "/api/auth/verify-email", json={"code": "000000"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(v.status_code, 400)

    async def test_verify_email_expired_code_rejected(self):
        token = (await self._signup()).json()["access_token"]
        async with self.Session() as s:
            row = (await s.execute(select(EmailVerificationToken))).scalar_one()
            row.expires_at = utc_now_naive() - timedelta(minutes=1)
            await s.commit()
            code = row.token
        v = await self.client.post(
            "/api/auth/verify-email", json={"code": code},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(v.status_code, 400)

    async def test_resend_issues_new_code_and_invalidates_old(self):
        token = (await self._signup()).json()["access_token"]
        first = await self._latest_code()
        rr = await self.client.post(
            "/api/auth/resend-verification",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(rr.status_code, 200)
        second = await self._latest_code()
        self.assertNotEqual(first, second)
        # The original code must no longer verify.
        bad = await self.client.post(
            "/api/auth/verify-email", json={"code": first},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(bad.status_code, 400)

    async def test_duplicate_email_rejected(self):
        await self._signup()
        r2 = await self._signup(username="creator2")
        self.assertEqual(r2.status_code, 409)

    async def test_login_accepts_username_or_email(self):
        await self._signup()
        for ident in ("creator", "creator@example.com"):
            r = await self.client.post(
                "/api/auth/login", json={"username": ident, "password": "supersecret1"}
            )
            self.assertEqual(r.status_code, 200, f"{ident}: {r.text}")

    @unittest.skipIf(auth_router._GOOGLE_CLIENT_ID, "Google OAuth configured in this env")
    async def test_google_unconfigured_returns_503(self):
        r = await self.client.post("/api/auth/google", json={"credential": "anything"})
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
