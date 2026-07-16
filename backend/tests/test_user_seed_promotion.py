"""User-upload → seed-pool promotion (_sync_user_seed).

A completed craft review with VERIFIED provider counts is introduced into the shared
seed pool as a source="user" SeedVideo. The craft scores are copied from the (already
counts-blind) live review; the rating is derived deterministically from the real counts
via score_outcome(). Promotion is idempotent, gated on consent, and never seeds minors.
"""
import json
import unittest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Base, SeedVideo, User, UserAnalysis
from routers.analyze import _sync_user_seed
from services.seed_analysis import score_outcome


_REVIEW = {
    "hook_velocity": 8,
    "cut_frequency": 6,
    "text_scannability": 7,
    "curiosity_gap": 5,
    "audio_visual_sync": 6,
    "loop_seamlessness": 4,
    "verdict": "Developing craft",
}


def _user(**kw) -> User:
    defaults = dict(
        username="creator",
        email="c@example.com",
        password_hash="x",
        birth_date="1995-01-01",   # adult
        seed_consent="ask",
    )
    defaults.update(kw)
    return User(**defaults)


def _analysis(**kw) -> UserAnalysis:
    defaults = dict(
        filename="clip.mp4",
        platform="tiktok",
        niche="Cooking",
        canonical_niche="Cooking",
        scores_json=json.dumps(_REVIEW),
        verdict="Developing craft",
        mode="craft_review",
        status="complete",
    )
    defaults.update(kw)
    return UserAnalysis(**defaults)


class UserSeedPromotionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_promotes_tiktok_with_verified_counts(self):
        async with self.sessions() as db:
            user = _user()
            db.add(user)
            await db.flush()
            a = _analysis(user_id=user.id, actual_views=20_000, actual_likes=1_800)
            db.add(a)
            await db.flush()

            await _sync_user_seed(db, a, user)
            await db.commit()

            self.assertIsNotNone(a.promoted_seed_id)
            seed = await db.get(SeedVideo, a.promoted_seed_id)
            self.assertEqual(seed.source, "user")
            self.assertEqual(seed.platform, "tiktok")
            self.assertEqual(seed.niche, "Cooking")
            self.assertEqual(seed.view_count, 20_000)
            self.assertEqual(seed.like_count, 1_800)
            expected_rating, expected_driver, _ = score_outcome(20_000, 1_800)
            self.assertEqual(seed.rating, expected_rating)
            blob = json.loads(seed.gemini_analysis)
            # Craft scores copied from the counts-blind review.
            self.assertEqual(blob["hook_velocity"], 8)
            self.assertEqual(blob["loop_seamlessness"], 4)
            # Outcome label is code-derived, not the model's.
            self.assertEqual(blob["performance_driver"], expected_driver)

    async def test_instagram_no_views_still_seeds(self):
        # Instagram hides views — the seed pool is otherwise empty for it. Likes-only
        # still yields a rating via score_outcome's absolute-like fallback.
        async with self.sessions() as db:
            user = _user()
            db.add(user)
            await db.flush()
            a = _analysis(
                user_id=user.id, platform="instagram", canonical_niche="Fitness",
                actual_views=None, actual_likes=25_000,
            )
            db.add(a)
            await db.flush()

            await _sync_user_seed(db, a, user)
            await db.commit()

            seed = await db.get(SeedVideo, a.promoted_seed_id)
            self.assertEqual(seed.platform, "instagram")
            self.assertIsNone(seed.view_count)
            self.assertEqual(seed.like_count, 25_000)
            self.assertEqual(seed.rating, score_outcome(None, 25_000)[0])

    async def test_refresh_updates_in_place_no_duplicate(self):
        async with self.sessions() as db:
            user = _user()
            db.add(user)
            await db.flush()
            a = _analysis(user_id=user.id, actual_views=20_000, actual_likes=1_800)
            db.add(a)
            await db.flush()

            await _sync_user_seed(db, a, user)
            await db.commit()
            first_id = a.promoted_seed_id

            # A later refresh with higher counts updates the SAME row.
            a.actual_views = 50_000
            a.actual_likes = 6_000
            await _sync_user_seed(db, a, user)
            await db.commit()

            self.assertEqual(a.promoted_seed_id, first_id)
            all_seeds = (await db.execute(select(SeedVideo))).scalars().all()
            self.assertEqual(len(all_seeds), 1)
            self.assertEqual(all_seeds[0].view_count, 50_000)
            self.assertEqual(all_seeds[0].like_count, 6_000)

    async def test_minor_never_seeded(self):
        async with self.sessions() as db:
            user = _user(birth_date="2012-01-01", seed_consent="no")  # minor
            db.add(user)
            await db.flush()
            a = _analysis(user_id=user.id, actual_views=20_000, actual_likes=1_800)
            db.add(a)
            await db.flush()

            await _sync_user_seed(db, a, user)
            await db.commit()

            self.assertIsNone(a.promoted_seed_id)
            self.assertEqual((await db.execute(select(SeedVideo))).scalars().first(), None)

    async def test_opted_out_not_seeded(self):
        async with self.sessions() as db:
            user = _user(seed_consent="no")
            db.add(user)
            await db.flush()
            a = _analysis(user_id=user.id, actual_views=20_000, actual_likes=1_800)
            db.add(a)
            await db.flush()

            await _sync_user_seed(db, a, user)
            await db.commit()
            self.assertIsNone(a.promoted_seed_id)

    async def test_no_counts_not_seeded(self):
        async with self.sessions() as db:
            user = _user()
            db.add(user)
            await db.flush()
            a = _analysis(user_id=user.id, actual_views=None, actual_likes=None)
            db.add(a)
            await db.flush()

            await _sync_user_seed(db, a, user)
            await db.commit()
            self.assertIsNone(a.promoted_seed_id)

    async def test_errored_review_not_seeded(self):
        async with self.sessions() as db:
            user = _user()
            db.add(user)
            await db.flush()
            a = _analysis(
                user_id=user.id, status="error",
                scores_json=json.dumps({"error": "Analysis failed."}),
                actual_views=20_000, actual_likes=1_800,
            )
            db.add(a)
            await db.flush()

            await _sync_user_seed(db, a, user)
            await db.commit()
            self.assertIsNone(a.promoted_seed_id)


if __name__ == "__main__":
    unittest.main()
