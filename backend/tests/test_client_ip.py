"""Regression tests for the spoof-resistant client-IP resolver.

Guards the fix for the X-Forwarded-For rate-limit bypass: keying a per-IP
throttle on the LEFTMOST XFF entry let any caller rotate the header to mint
unlimited fresh buckets (defeating the guest analysis cap, the upload cap, and
the password-reset / email-verify brute-force guards). The resolver must trust
only the rightmost hop(s) we control.
"""
import unittest

import services.throttle as throttle
from services.throttle import client_ip, check_rate


class _Headers(dict):
    """Minimal stand-in for Starlette's case-insensitive Headers.get()."""
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


class ClientIpTest(unittest.TestCase):
    def setUp(self):
        # Tests assume the Railway default of one trusted hop.
        self._orig = throttle._TRUSTED_PROXY_HOPS
        throttle._TRUSTED_PROXY_HOPS = 1

    def tearDown(self):
        throttle._TRUSTED_PROXY_HOPS = self._orig

    def test_no_xff_falls_back_to_socket_peer(self):
        self.assertEqual(client_ip(_FakeRequest(xff=None, peer="198.51.100.7")), "198.51.100.7")

    def test_no_xff_no_peer_returns_unknown(self):
        self.assertEqual(client_ip(_FakeRequest(xff=None, peer=None)), "unknown")

    def test_single_entry_is_the_real_client(self):
        # Railway with a direct client: Envoy sets XFF to the one real peer.
        self.assertEqual(client_ip(_FakeRequest(xff="198.51.100.7")), "198.51.100.7")

    def test_spoofed_prefix_is_ignored_rightmost_wins(self):
        # Attacker sends XFF: <spoof>; Railway APPENDS the real peer on the right.
        req = _FakeRequest(xff="1.2.3.4, 198.51.100.7")
        self.assertEqual(client_ip(req), "198.51.100.7")

    def test_many_spoofed_entries_still_ignored(self):
        req = _FakeRequest(xff="9.9.9.9, 8.8.8.8, 7.7.7.7, 198.51.100.7")
        self.assertEqual(client_ip(req), "198.51.100.7")

    def test_whitespace_and_empty_entries_tolerated(self):
        self.assertEqual(client_ip(_FakeRequest(xff="  , , 198.51.100.7  ")), "198.51.100.7")

    def test_two_trusted_hops_takes_second_from_right(self):
        throttle._TRUSTED_PROXY_HOPS = 2
        req = _FakeRequest(xff="1.2.3.4, 198.51.100.7, 10.0.0.1")
        # With 2 trusted hops, the real client is the 2nd-from-right.
        self.assertEqual(client_ip(req), "198.51.100.7")

    def test_xff_rotation_no_longer_mints_fresh_buckets(self):
        """End-to-end: rotating the spoofable prefix maps to ONE throttle bucket,
        so the per-IP limit actually fires instead of being bypassed."""
        allowed = 0
        for i in range(10):
            req = _FakeRequest(xff=f"10.0.0.{i}, 198.51.100.50")  # real peer constant
            if check_rate(f"test-bucket:{client_ip(req)}", max_hits=5, window_seconds=600):
                allowed += 1
        # Exactly the cap is granted despite 10 distinct spoofed prefixes.
        self.assertEqual(allowed, 5)


if __name__ == "__main__":
    unittest.main()
