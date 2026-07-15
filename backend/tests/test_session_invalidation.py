"""Regression tests for the security fixes around session/token lifecycle and
account deletion.

Covers:
  - Password RESET bumps token_version so tokens minted beforehand stop working
    (a stolen token can't outlive a credential reset).
  - Password CHANGE rotates the token: other sessions die, the caller gets a
    fresh working token back.
  - Account deletion removes the user's email_verification_tokens (the missing
    delete previously made deletion crash on Postgres, where FKs are enforced).

Same hermetic harness as test_auth_flow: real app over httpx ASGI transport,
in-memory SQLite, email transport stubbed. Each test uses a distinct
X-Forwarded-For so the process-wide login/reset throttle buckets don't collide.
"""
import unittest
import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import get_db
from main import app
from models import Base, EmailVerificationToken, PasswordResetToken, User, UserAnalysis
from routers import auth as auth_router


class SessionInvalidationTest(unittest.IsolatedAsyncioTestCase):
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

        self.sent: list[tuple] = []
        self._orig_send = auth_router._send_email

        async def _fake_send(to_email, subject, html, plain):
            self.sent.append((to_email, subject))
            return True

        auth_router._send_email = _fake_send
        # Unique source IP per test → its own throttle bucket.
        self._ip = f"203.0.113.{id(self) % 250 + 1}"
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Forwarded-For": self._ip},
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        auth_router._send_email = self._orig_send
        app.dependency_overrides.pop(get_db, None)
        await self.engine.dispose()

    async def _signup(self, email="creator@example.com", username="creator", password="supersecret1"):
        # Override the client's default XFF with a unique per-call IP: signup is
        # IP-throttled (5/900s) with process-global state, and self._ip (id-based)
        # isn't guaranteed unique across tests. The reset/login throttles below
        # keep using self._ip via the client default — those keys don't collide.
        r = await self.client.post("/api/auth/signup", json={
            "email": email, "username": username,
            "password": password, "birth_date": "1995-06-15",
        }, headers={"X-Forwarded-For": f"signup-{uuid.uuid4()}"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["access_token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    async def _reset_code_for(self, user_id: int) -> str:
        async with self.Session() as s:
            return (await s.execute(
                select(PasswordResetToken.token)
                .where(PasswordResetToken.user_id == user_id)
                .order_by(PasswordResetToken.id.desc())
            )).scalars().first()

    # ── Password reset invalidates pre-reset tokens ──────────────────────────
    async def test_password_reset_invalidates_old_tokens(self):
        old_token = await self._signup()
        # Sanity: the token works before the reset.
        me = await self.client.get("/api/auth/me", headers=self._auth(old_token))
        self.assertEqual(me.status_code, 200, me.text)

        # Trigger a reset and pull the emailed code straight from the DB.
        fp = await self.client.post("/api/auth/forgot-password", json={"email": "creator@example.com"})
        self.assertEqual(fp.status_code, 200)
        async with self.Session() as s:
            uid = (await s.execute(select(User.id).where(User.email == "creator@example.com"))).scalar_one()
        code = await self._reset_code_for(uid)
        self.assertIsNotNone(code)

        rp = await self.client.post("/api/auth/reset-password", json={
            "token": code, "email": "creator@example.com", "new_password": "brandnewpass9",
        })
        self.assertEqual(rp.status_code, 200, rp.text)

        # The pre-reset token must now be rejected.
        me_after = await self.client.get("/api/auth/me", headers=self._auth(old_token))
        self.assertEqual(me_after.status_code, 401)

        # A fresh login with the new password works.
        login = await self.client.post("/api/auth/login", json={
            "username": "creator", "password": "brandnewpass9",
        })
        self.assertEqual(login.status_code, 200, login.text)
        new_token = login.json()["access_token"]
        me_new = await self.client.get("/api/auth/me", headers=self._auth(new_token))
        self.assertEqual(me_new.status_code, 200)

    # ── Password change rotates the token (keeps caller, kills other sessions) ─
    async def test_change_password_rotates_token(self):
        old_token = await self._signup()
        resp = await self.client.patch("/api/me/password", headers=self._auth(old_token), json={
            "current_password": "supersecret1", "new_password": "anothergoodpw1",
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        new_token = resp.json().get("access_token")
        self.assertTrue(new_token, "change-password must return a fresh token")
        self.assertNotEqual(new_token, old_token)

        # Old session is dead; the returned token still works.
        old_me = await self.client.get("/api/auth/me", headers=self._auth(old_token))
        self.assertEqual(old_me.status_code, 401)
        new_me = await self.client.get("/api/auth/me", headers=self._auth(new_token))
        self.assertEqual(new_me.status_code, 200)

    # ── Account deletion removes email-verification tokens (the FK fix) ───────
    async def test_delete_account_removes_verification_tokens(self):
        token = await self._signup()
        async with self.Session() as s:
            uid = (await s.execute(select(User.id).where(User.email == "creator@example.com"))).scalar_one()
            n_codes = (await s.execute(
                select(EmailVerificationToken).where(EmailVerificationToken.user_id == uid)
            )).scalars().all()
        self.assertGreaterEqual(len(n_codes), 1, "signup should create a verification code row")

        # DELETE takes a JSON body — use request() so httpx sends it.
        resp = await self.client.request(
            "DELETE", "/api/me/account", headers=self._auth(token),
            json={"password": "supersecret1"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        async with self.Session() as s:
            self.assertIsNone(
                (await s.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            )
            remaining = (await s.execute(
                select(EmailVerificationToken).where(EmailVerificationToken.user_id == uid)
            )).scalars().all()
        self.assertEqual(remaining, [], "verification tokens must be deleted with the account")

    # ── /status endpoint visibility (no cross-tenant existence/status oracle) ──
    async def _insert_analysis(self, user_id, status="processing") -> int:
        async with self.Session() as s:
            row = UserAnalysis(
                user_id=user_id, platform="tiktok", filename="x.mp4", niche="test",
                scores_json="{}", verdict="", status=status,
            )
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return row.id

    async def test_status_visible_for_unclaimed_guest_row(self):
        aid = await self._insert_analysis(user_id=None, status="pending")
        # No auth header on this one request (guest polling their own upload).
        r = await self.client.get(f"/api/analyses/{aid}/status", headers={"Authorization": ""})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "pending")

    async def test_status_hidden_from_non_owner_of_claimed_row(self):
        owner_token = await self._signup(email="owner@example.com", username="owner")
        async with self.Session() as s:
            owner_id = (await s.execute(select(User.id).where(User.email == "owner@example.com"))).scalar_one()
        aid = await self._insert_analysis(user_id=owner_id, status="processing")

        # Owner (authenticated) can see it.
        mine = await self.client.get(f"/api/analyses/{aid}/status", headers=self._auth(owner_token))
        self.assertEqual(mine.status_code, 200, mine.text)

        # A logged-in stranger gets 404 — no existence/status leak.
        stranger_token = await self._signup(email="stranger@example.com", username="stranger")
        theirs = await self.client.get(f"/api/analyses/{aid}/status", headers=self._auth(stranger_token))
        self.assertEqual(theirs.status_code, 404)

        # Anonymous caller on a CLAIMED row also gets 404.
        anon = await self.client.get(f"/api/analyses/{aid}/status", headers={"Authorization": ""})
        self.assertEqual(anon.status_code, 404)


if __name__ == "__main__":
    unittest.main()
