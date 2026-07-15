"""The direct upload / TikTok-URL analyze path is now non-blocking: it creates a
"pending" row, commits (releasing the pooled DB connection), and finalizes the
Gemini result in a BackgroundTask — instead of holding a connection + open
transaction across the 30–90s Gemini call. These tests pin that contract:

  - POST /api/analyze (file OR TikTok URL) returns {"id", "status": "pending"}
    immediately (a guest also gets a claim_token).
  - The background task finalizes the row to status="complete" with the verdict.

The background task opens its own session via the module-level AsyncSessionLocal,
so we repoint it at the in-memory test engine. Each request uses a unique
X-Forwarded-For so the process-global guest throttle doesn't bleed across tests.
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
from models import Base, UserAnalysis
from routers import analyze as analyze_router
from routers import auth as auth_router


class DirectAnalyzeBackgroundTest(unittest.IsolatedAsyncioTestCase):
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

        # A successful Gemini review: returns a real result dict (no "error" key).
        self._orig_analyze = analyze_router.analyze_video

        async def _fake_ok_analyze(*args, **kwargs):
            return {"verdict": "Ship it", "hook_velocity": 8}

        analyze_router.analyze_video = _fake_ok_analyze

        # TikTok-URL branch: stub the network fetch so it returns bytes + caption.
        self._orig_dl = analyze_router.download_tiktok_video

        async def _fake_download(url):
            return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64, "auto caption"

        analyze_router.download_tiktok_video = _fake_download

        # Background finalize uses the module-level AsyncSessionLocal — point it at
        # the in-memory test engine so it shares this test's DB.
        self._orig_sessionlocal = analyze_router.AsyncSessionLocal
        analyze_router.AsyncSessionLocal = self.Session

        self._orig_send = auth_router._send_email

        async def _fake_send(*args, **kwargs):
            return True

        auth_router._send_email = _fake_send
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        analyze_router.analyze_video = self._orig_analyze
        analyze_router.download_tiktok_video = self._orig_dl
        analyze_router.AsyncSessionLocal = self._orig_sessionlocal
        auth_router._send_email = self._orig_send
        app.dependency_overrides.pop(get_db, None)
        await self.engine.dispose()

    def _file(self):
        return {"file": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64, "video/mp4")}

    def _ip(self):
        return {"X-Forwarded-For": f"analyze-{uuid.uuid4()}"}

    async def test_file_upload_returns_pending_then_completes(self):
        r = await self.client.post(
            "/api/analyze", files=self._file(), data={"platform": "tiktok"}, headers=self._ip()
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "pending")
        self.assertIn("id", body)
        # Guest upload hands back a claim token so the browser can claim it later.
        self.assertIn("claim_token", body)

        # The background task ran within the request cycle and finalized the row.
        async with self.Session() as db:
            row = (await db.execute(
                select(UserAnalysis).where(UserAnalysis.id == body["id"])
            )).scalar_one()
            self.assertEqual(row.status, "complete")
            self.assertEqual(row.verdict, "Ship it")

    async def test_tiktok_url_returns_pending_then_completes(self):
        r = await self.client.post(
            "/api/analyze",
            data={"video_url": "https://www.tiktok.com/@creator/video/123"},
            headers=self._ip(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "pending")

        async with self.Session() as db:
            row = (await db.execute(
                select(UserAnalysis).where(UserAnalysis.id == body["id"])
            )).scalar_one()
            self.assertEqual(row.status, "complete")
            self.assertEqual(row.verdict, "Ship it")


if __name__ == "__main__":
    unittest.main()
