"""Single source of truth for the app's clock.

The database DateTime columns are timezone-NAIVE UTC, and the whole codebase
compares against naive values. ``datetime.utcnow()`` also returns naive UTC but
is deprecated (scheduled for removal in a future Python). ``utc_now_naive()`` is
the behaviour-preserving replacement: the same naive-UTC value via the
non-deprecated ``datetime.now(timezone.utc)``, with the tzinfo stripped so it
stays comparable to the stored columns. Never mix aware and naive datetimes —
always go through this helper.
"""
from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """Return the current UTC time without tzinfo (matches the DB columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
