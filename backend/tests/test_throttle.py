"""The abuse-guard throttle and the presigned-upload store are now DB-backed
(rate_limit_hits / pending_uploads tables) instead of per-process memory, so their
limits and keys hold across workers and replicas. These tests pin that:

  - the sliding-window limit still fires at the cap (unchanged from a caller's view);
  - hits and upload keys written by one session are visible to ANOTHER session —
    i.e. a second "worker" enforces the same limit and can consume a key issued by
    the first (the whole point of moving off in-memory state);
  - expired hits drop out of the window;
  - rotating a spoofable X-Forwarded-For prefix still maps to ONE bucket.

Two independent AsyncSessions over one shared in-memory DB stand in for two worker
processes hitting the same Postgres.
"""
import unittest
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, RateLimitHit
from routers.analyze import _pop_pending, _record_pending
from services.clock import utc_now_naive
from services.throttle import check_rate, client_ip


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, xff=None, peer="203.0.113.9"):
        h = {}
        if xff is not None:
            h["x-forwarded-for"] = xff
        self.headers = _Headers(h)
        self.client = _FakeClient(peer) if peer else None


class ThrottleTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_limit_enforced_within_window(self):
        async with self.Session() as s:
            allowed = [await check_rate(s, "k", 5, 600) for _ in range(8)]
        # Exactly the cap is granted; the rest are rejected.
        self.assertEqual(allowed, [True] * 5 + [False] * 3)

    async def test_counters_shared_across_sessions(self):
        key = "shared-key"
        # "Worker A" fills the cap.
        async with self.Session() as a:
            for _ in range(3):
                self.assertTrue(await check_rate(a, key, max_hits=3, window_seconds=600))
        # "Worker B" — a separate session/process — sees A's hits and is blocked.
        async with self.Session() as b:
            self.assertFalse(await check_rate(b, key, max_hits=3, window_seconds=600))

    async def test_distinct_keys_have_independent_buckets(self):
        async with self.Session() as s:
            for _ in range(3):
                await check_rate(s, "key-a", 3, 600)
            # A different key is untouched by key-a's hits.
            self.assertTrue(await check_rate(s, "key-b", 3, 600))

    async def test_expired_hits_drop_out_of_window(self):
        key = "expiry"
        async with self.Session() as s:
            for _ in range(3):
                await check_rate(s, key, 3, 600)
        # Age every stored hit past the window.
        async with self.Session() as s:
            await s.execute(
                update(RateLimitHit)
                .where(RateLimitHit.key == key)
                .values(hit_at=utc_now_naive() - timedelta(seconds=601))
            )
            await s.commit()
        # With all prior hits expired, a fresh hit is admitted again.
        async with self.Session() as s:
            self.assertTrue(await check_rate(s, key, 3, 600))

    async def test_xff_rotation_maps_to_one_bucket(self):
        """Rotating the spoofable XFF prefix collapses to ONE bucket, so the per-IP
        cap fires instead of being bypassed (client_ip + DB-backed check_rate)."""
        allowed = 0
        async with self.Session() as s:
            for i in range(10):
                req = _FakeRequest(xff=f"10.0.0.{i}, 198.51.100.50")  # real peer constant
                if await check_rate(s, f"test-bucket:{client_ip(req)}", max_hits=5, window_seconds=600):
                    allowed += 1
        self.assertEqual(allowed, 5)

    async def test_pending_upload_record_and_pop_across_sessions(self):
        key = "uploads/abc_clip.mp4"
        # "Worker A" issues the presigned key.
        async with self.Session() as a:
            await _record_pending(a, key, user_id=42, issuer_ip="203.0.113.5")
        # "Worker B" consumes the key issued by A.
        async with self.Session() as b:
            entry = await _pop_pending(b, key)
            await b.commit()
        self.assertIsNotNone(entry)
        self.assertEqual(entry[0], 42)             # user_id
        self.assertEqual(entry[1], "203.0.113.5")  # issuer_ip
        # Consumed exactly once: a later pop finds nothing.
        async with self.Session() as c:
            self.assertIsNone(await _pop_pending(c, key))

    async def test_pending_upload_supports_guest_null_user(self):
        key = "uploads/guest_clip.mp4"
        async with self.Session() as a:
            await _record_pending(a, key, user_id=None, issuer_ip="198.51.100.9")
        async with self.Session() as b:
            entry = await _pop_pending(b, key)
            await b.commit()
        self.assertIsNotNone(entry)
        self.assertIsNone(entry[0])                # guest → NULL user_id
        self.assertEqual(entry[1], "198.51.100.9")


if __name__ == "__main__":
    unittest.main()
