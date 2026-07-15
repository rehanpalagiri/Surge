import unittest
import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import get_db
from main import app
from models import Base, UserAnalysis
from routers import auth as auth_router


class ClaimAnalysisTest(unittest.IsolatedAsyncioTestCase):
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
        self._orig_send = auth_router._send_email

        async def _fake_send(*args, **kwargs):
            return True

        auth_router._send_email = _fake_send
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        auth_router._send_email = self._orig_send
        app.dependency_overrides.pop(get_db, None)
        await self.engine.dispose()

    async def _signup_token(self) -> str:
        # Unique per-call IP: signup is IP-throttled (5/900s) with process-global state.
        r = await self.client.post("/api/auth/signup", json={
            "email": "owner@example.com",
            "username": "owner",
            "password": "supersecret1",
            "birth_date": "1995-06-15",
        }, headers={"X-Forwarded-For": f"signup-{uuid.uuid4()}"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["access_token"]

    async def _guest_analysis(self, claim_token: str = "secret-token") -> int:
        async with self.Session() as db:
            row = UserAnalysis(
                user_id=None,
                platform="tiktok",
                filename="guest.mp4",
                niche="Auto-detected",
                scores_json="{}",
                verdict="Needs revision",
                mode="craft_review",
                status="complete",
                guest_claim_token=claim_token,
            )
            db.add(row)
            await db.commit()
            return row.id

    async def test_guest_claim_requires_matching_token_and_clears_it(self):
        auth = {"Authorization": f"Bearer {await self._signup_token()}"}
        analysis_id = await self._guest_analysis()

        missing = await self.client.post(f"/api/analyses/{analysis_id}/claim", json={}, headers=auth)
        self.assertEqual(missing.status_code, 403)

        bad = await self.client.post(
            f"/api/analyses/{analysis_id}/claim",
            json={"claim_token": "wrong"},
            headers=auth,
        )
        self.assertEqual(bad.status_code, 403)

        ok = await self.client.post(
            f"/api/analyses/{analysis_id}/claim",
            json={"claim_token": "secret-token"},
            headers=auth,
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertIsNone(ok.json().get("claim_token"))

        async with self.Session() as db:
            row = (await db.execute(
                select(UserAnalysis).where(UserAnalysis.id == analysis_id)
            )).scalar_one()
            self.assertIsNotNone(row.user_id)
            self.assertIsNone(row.guest_claim_token)


if __name__ == "__main__":
    unittest.main()
