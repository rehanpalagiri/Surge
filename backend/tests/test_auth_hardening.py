"""Hardening tests added in the pre-deploy audit:
  - login is rate-limited per IP (brute-force guard)
  - password-reset codes are scoped to the account's email (defense in depth)

Each test uses a distinct X-Forwarded-For so the process-wide in-memory throttle
state can't bleed between tests.
"""
import unittest

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, PasswordResetToken, User
from services.clock import utc_now_naive
from datetime import timedelta


class AuthHardeningTest(unittest.IsolatedAsyncioTestCase):
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
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.pop(get_db, None)
        await self.engine.dispose()

    async def _make_user(self, username, email, password="password123"):
        async with self.Session() as db:
            u = User(username=username, email=email, password_hash=hash_password(password),
                     email_verified=True)
            db.add(u)
            await db.commit()
            return u.id

    async def test_login_is_rate_limited_per_ip(self):
        await self._make_user("alice", "alice@example.com")
        ip = {"X-Forwarded-For": "203.0.113.10"}
        # 10 wrong-password attempts are allowed through (401), the 11th is throttled.
        for _ in range(10):
            r = await self.client.post("/api/auth/login",
                                       json={"username": "alice", "password": "wrong"}, headers=ip)
            self.assertEqual(r.status_code, 401, r.text)
        throttled = await self.client.post("/api/auth/login",
                                           json={"username": "alice", "password": "wrong"}, headers=ip)
        self.assertEqual(throttled.status_code, 429)

    async def test_login_throttle_is_per_ip_not_global(self):
        await self._make_user("bob", "bob@example.com")
        # A different IP is unaffected by another IP's attempts.
        for _ in range(10):
            await self.client.post("/api/auth/login",
                                   json={"username": "bob", "password": "wrong"},
                                   headers={"X-Forwarded-For": "203.0.113.20"})
        r = await self.client.post("/api/auth/login",
                                   json={"username": "bob", "password": "password123"},
                                   headers={"X-Forwarded-For": "203.0.113.21"})
        self.assertEqual(r.status_code, 200, "a fresh IP must still be able to log in")

    async def _seed_reset_token(self, user_id, token="111111"):
        async with self.Session() as db:
            db.add(PasswordResetToken(user_id=user_id, token=token,
                                      expires_at=utc_now_naive() + timedelta(hours=1)))
            await db.commit()

    async def test_reset_code_is_scoped_to_email(self):
        a = await self._make_user("ann", "ann@example.com")
        await self._make_user("eve", "eve@example.com")
        await self._seed_reset_token(a, "424242")

        # Eve supplies Ann's code but her own email -> rejected (scoped to Eve).
        wrong = await self.client.post("/api/auth/verify-reset-code",
                                       json={"token": "424242", "email": "eve@example.com"},
                                       headers={"X-Forwarded-For": "203.0.113.30"})
        self.assertEqual(wrong.status_code, 400)

        # Correct owner email -> valid.
        right = await self.client.post("/api/auth/verify-reset-code",
                                       json={"token": "424242", "email": "ann@example.com"},
                                       headers={"X-Forwarded-For": "203.0.113.31"})
        self.assertEqual(right.status_code, 200)
        self.assertTrue(right.json()["valid"])

    async def test_reset_password_rejects_wrong_email(self):
        a = await self._make_user("carl", "carl@example.com")
        await self._make_user("mallory", "mallory@example.com")
        await self._seed_reset_token(a, "999000")
        # Mallory tries to use Carl's code under her email -> cannot reset.
        r = await self.client.post("/api/auth/reset-password",
                                   json={"token": "999000", "new_password": "newpass12345",
                                         "email": "mallory@example.com"},
                                   headers={"X-Forwarded-For": "203.0.113.40"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
