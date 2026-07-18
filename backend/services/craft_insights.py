"""Shared craft-scoring constants and helpers used by offline analysis tools.

Not a user-facing feature — read by tools/craft_correlation.py, tools/score_distribution.py,
and services/seed_statistics.py, which all need the same dimension set, verified-source
list, and view-rate floor to keep their sample-size and honesty guarantees consistent.
"""
from __future__ import annotations

import json

DIMENSIONS = (
    "hook_velocity", "cut_frequency", "text_scannability",
    "curiosity_gap", "audio_visual_sync", "loop_seamlessness",
)
DIMENSION_LABELS = {
    "hook_velocity": "Hook Velocity",
    "cut_frequency": "Cut Frequency",
    "text_scannability": "Text Scannability",
    "curiosity_gap": "Curiosity Gap",
    "audio_visual_sync": "Audio-Visual Sync",
    "loop_seamlessness": "Ending Strength",
}

# A like rate on very few views is noise: its resolution is one like = 1/views.
# Requiring 1/views <= 0.01 (a single like moves the observed rate by <= 1 point)
# floors this at 100 views. Below it we do not treat likes/views as an observed rate.
MIN_VIEWS_FOR_RATE = 100
# Provider sources we treat as verified (vs user-asserted manual entries).
VERIFIED_SOURCES = ("tikwm", "rapidapi", "hikerapi")
HORIZON_ORDER = {"24h": 0, "7d": 1, "30d": 2}


def _craft_scores(scores_json: str) -> dict | None:
    """Return the six dimension scores. A dimension the review marked
    not_applicable (deliberate format choice, craft_review_version >= 4)
    comes back as None; any other missing/invalid score voids the row."""
    try:
        data = json.loads(scores_json)
    except (ValueError, TypeError):
        return None
    na = data.get("not_applicable")
    na_keys = set(na) if isinstance(na, dict) else set()
    out = {}
    for key in DIMENSIONS:
        v = data.get(key)
        if v is None and key in na_keys:
            out[key] = None
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        out[key] = float(v)
    return out
