"""tikwm fetch resilience: bounded retry/backoff on 429/5xx and diagnosable
error capture (HTTP status + body snippet) rather than a bare exception class."""
import unittest
from unittest.mock import AsyncMock, patch

import services.tiktok_fetch as tf


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class FakeClient:
    """Async context manager whose .get() replays a scripted list of responses."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, *args, **kwargs):
        self.calls += 1
        return self._responses.pop(0)


def _ok_payload():
    return {
        "code": 0,
        "data": {
            "id": "123", "play": "https://cdn/v.mp4",
            "play_count": 1000, "digg_count": 200,
            "comment_count": 10, "share_count": 5, "collect_count": 3,
            "title": "hi", "create_time": 1_700_000_000,
            "author": {"unique_id": "creator", "follower_count": 999},
        },
    }


class TikTokFetchRetryTest(unittest.IsolatedAsyncioTestCase):
    async def _run(self, responses):
        client = FakeClient(responses)
        events = []

        async def _capture(**kwargs):
            events.append(kwargs)

        with patch.object(tf.httpx, "AsyncClient", return_value=client), \
             patch.object(tf.asyncio, "sleep", new=AsyncMock()) as sleep_mock, \
             patch.object(tf, "record_usage_event", new=_capture):
            try:
                result = await tf.fetch_tiktok("https://www.tiktok.com/@c/video/123")
                err = None
            except Exception as e:  # noqa: BLE001
                result, err = None, e
        return result, err, client, sleep_mock, events

    async def test_retries_then_succeeds_on_transient_429(self):
        result, err, client, sleep_mock, events = await self._run(
            [FakeResponse(429, text="rate limited"), FakeResponse(200, _ok_payload())]
        )
        self.assertIsNone(err)
        self.assertEqual(client.calls, 2)              # one retry
        self.assertEqual(sleep_mock.await_count, 1)    # one backoff
        self.assertEqual(result["view_count"], 1000)
        self.assertEqual(result["like_count"], 200)
        self.assertTrue(events and events[-1]["success"] is True)

    async def test_terminal_429_is_bounded_and_diagnosable(self):
        result, err, client, sleep_mock, events = await self._run(
            [FakeResponse(429, text="Too Many Requests"),
             FakeResponse(429, text="Too Many Requests"),
             FakeResponse(429, text="Too Many Requests")]
        )
        self.assertIsInstance(err, ValueError)
        self.assertIn("429", str(err))                 # status in the message
        self.assertIn("Too Many Requests", str(err))   # body snippet in the message
        self.assertEqual(client.calls, tf._MAX_ATTEMPTS)   # bounded, no infinite loop
        self.assertEqual(sleep_mock.await_count, tf._MAX_ATTEMPTS - 1)
        # telemetry records the precise status, not just "HTTPStatusError"
        self.assertEqual(events[-1]["error_code"], "http_429")
        self.assertIs(events[-1]["success"], False)

    async def test_5xx_is_retried(self):
        result, err, client, sleep_mock, events = await self._run(
            [FakeResponse(503, text="unavailable"), FakeResponse(200, _ok_payload())]
        )
        self.assertIsNone(err)
        self.assertEqual(client.calls, 2)

    async def test_nonzero_api_code_records_precise_error(self):
        result, err, client, sleep_mock, events = await self._run(
            [FakeResponse(200, {"code": -1, "msg": "video not found"})]
        )
        self.assertIsInstance(err, ValueError)
        self.assertEqual(events[-1]["error_code"], "tikwm_nonzero_code")
        self.assertIs(events[-1]["success"], False)


if __name__ == "__main__":
    unittest.main()
