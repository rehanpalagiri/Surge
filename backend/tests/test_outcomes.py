from datetime import datetime, timedelta, timezone
import unittest

from services.outcomes import maturity_window, post_id_from_url


class OutcomeHelpersTest(unittest.TestCase):
    def test_supported_maturity_windows(self):
        posted = datetime(2026, 1, 1, 12, 0)
        for label, hours in (("24h", 24), ("7d", 168), ("30d", 720)):
            age, horizon = maturity_window(posted, posted + timedelta(hours=hours))
            self.assertEqual(age, hours)
            self.assertEqual(horizon, label)

    def test_off_window_observation_is_not_labeled(self):
        posted = datetime(2026, 1, 1, 12, 0)
        age, horizon = maturity_window(posted, posted + timedelta(hours=80))
        self.assertEqual(age, 80)
        self.assertIsNone(horizon)

    def test_missing_post_time_never_invents_horizon(self):
        self.assertEqual(maturity_window(None, datetime.now(timezone.utc)), (None, None))

    def test_platform_post_ids(self):
        self.assertEqual(
            post_id_from_url("https://www.tiktok.com/@creator/video/123456789?x=1", "tiktok"),
            "123456789",
        )
        self.assertEqual(
            post_id_from_url("https://www.instagram.com/reel/AbC_def-1/", "instagram"),
            "AbC_def-1",
        )


if __name__ == "__main__":
    unittest.main()
