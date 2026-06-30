"""Regression tests: a non-429 Gemini failure must NOT masquerade as a finished
review.

When analyze_video can't produce a real report (timeout, file-processing error,
5xx, unparseable JSON) it returns an error dict with all-zero scores instead of
raising. Before the fix the router stored that as status="complete", which (a)
charged authenticated users a rate-limit credit for a report they never got and
(b) showed guests a locked card reading 0/10 across every dimension instead of a
failure screen. These tests pin the corrected behaviour.
"""
import unittest

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import get_db
from main import app
from models import Base, User, UserAnalysis
from routers import analyze as analyze_router
from routers import auth as auth_router
from services.gemini import _error_dict
from services.rate_limit import get_rate_limit


class FailedAnalysisTest(unittest.IsolatedAsyncioTestCase):
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

        # Stand in for a transient Gemini failure: returns an error dict, no raise.
        self._orig_analyze = analyze_router.analyze_video

        async def _fake_failed_analyze(*args, **kwargs):
            return _error_dict("Video processing timed out.")

        analyze_router.analyze_video = _fake_failed_analyze

        # Don't send real email on signup.
        self._orig_send = auth_router._send_email

        async def _fake_send(*args, **kwargs):
            return True

        auth_router._send_email = _fake_send
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        analyze_router.analyze_video = self._orig_analyze
        auth_router._send_email = self._orig_send
        app.dependency_overrides.pop(get_db, None)
        await self.engine.dispose()

    def _file(self):
        return {"file": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64, "video/mp4")}

    async def _signup_token(self) -> str:
        r = await self.client.post("/api/auth/signup", json={
            "email": "creator@example.com", "username": "creator",
            "password": "supersecret1", "birth_date": "1995-06-15",
        })
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["access_token"]

    async def test_guest_failed_analysis_marked_error_and_visible_in_locked_view(self):
        r = await self.client.post("/api/analyze", files=self._file(), data={"platform": "tiktok"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        analysis_id = body["id"]
        # Immediate response surfaces the failure.
        self.assertIn("error", body["scores_json"])

        # Stored row is flagged error, not a bogus "complete".
        async with self.Session() as db:
            row = (await db.execute(
                select(UserAnalysis).where(UserAnalysis.id == analysis_id)
            )).scalar_one()
            self.assertEqual(row.status, "error")

        # A guest reloading the (locked) analysis still sees the failure screen
        # signal — the error key is propagated into the locked payload.
        locked = await self.client.get(f"/api/analyses/{analysis_id}")
        self.assertEqual(locked.status_code, 200)
        self.assertTrue(locked.json()["scores_json"].get("locked"))
        self.assertIn("error", locked.json()["scores_json"])

    async def test_authenticated_user_not_charged_a_credit_for_a_failure(self):
        token = await self._signup_token()
        auth = {"Authorization": f"Bearer {token}"}

        r = await self.client.post("/api/analyze", files=self._file(), data={"platform": "tiktok"}, headers=auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("error", r.json()["scores_json"])

        # The failed analysis must not consume one of the user's rate-limit slots.
        async with self.Session() as db:
            analysis = (await db.execute(select(UserAnalysis))).scalars().first()
            user_obj = (await db.execute(
                select(User).where(User.id == analysis.user_id)
            )).scalar_one()
            rl = await get_rate_limit(user_obj, db)
        self.assertEqual(rl["used"], 0, "failed analysis should not consume a credit")
        self.assertEqual(rl["remaining"], rl["effective_limit"])


if __name__ == "__main__":
    unittest.main()
