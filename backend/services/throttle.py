"""In-memory sliding-window throttle for abuse-sensitive auth endpoints.

Single-process only (Render runs one instance) — state lives in memory and
resets on deploy/restart, which is acceptable for this threat model: an attacker
can't force a restart, and the windows here are minutes-to-an-hour. This is NOT a
substitute for the DB-backed upload limiter (services/rate_limit.py); it's purely
a brute-force / spam guard on the password-reset endpoints, which have no auth and
match reset codes globally by a 6-digit value.

If the backend is ever scaled to multiple instances, move this to a shared store
(Redis) or a DB table — per-instance counters would each allow the full quota.
"""
import time
from collections import defaultdict, deque
from threading import Lock

_hits: dict[str, deque] = defaultdict(deque)
_lock = Lock()
_calls = 0
_SWEEP_EVERY = 5000          # purge idle keys every N calls to bound memory
_MAX_WINDOW = 3600           # longest window any caller uses (seconds)


def check_rate(key: str, max_hits: int, window_seconds: int) -> bool:
    """Record a hit for ``key`` and return True if it's within the limit.

    Returns False (without recording) once ``key`` has already reached
    ``max_hits`` within the trailing ``window_seconds``. Uses a monotonic
    clock so it's immune to wall-clock adjustments.
    """
    global _calls
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        _calls += 1
        if _calls % _SWEEP_EVERY == 0:
            _sweep(now)
        dq = _hits[key]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= max_hits:
            return False
        dq.append(now)
        return True


def _sweep(now: float) -> None:
    """Drop keys with no hits inside the longest window — bounds memory under
    a flood of unique keys (e.g. spoofed X-Forwarded-For IPs)."""
    stale = now - _MAX_WINDOW
    for k in list(_hits.keys()):
        dq = _hits[k]
        while dq and dq[0] < stale:
            dq.popleft()
        if not dq:
            del _hits[k]
