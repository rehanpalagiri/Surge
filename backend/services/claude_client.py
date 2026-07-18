"""Thin Claude (Anthropic) call wrapper — the Claude-side counterpart to
services/telemetry.py's Gemini wrapper.

Used only by offline, admin/scheduler-triggered synthesis (services/seed_insights.py,
services/trend_insights.py) — never in the live per-video request path — so one
non-streaming call per niche, well under the ~16K-output threshold where the SDK
requires streaming, is the right shape. Model is fixed to Claude Opus 4.8: this step
never re-watches video (it narrates numbers already computed by
services/seed_statistics.py), runs weekly rather than per-upload, and the cost gap to
a cheaper tier that mattered for the per-video Gemini scoring call doesn't apply here.
"""
from __future__ import annotations

import os
import time

from anthropic import AsyncAnthropic

from services.telemetry import record_usage_event

CLAUDE_OPUS_MODEL = "claude-opus-4-8"
# Public list price (USD per 1M tokens). Overridable to a contracted rate via env
# without a code change — same pattern as the Gemini prices in services/telemetry.py.
_DEFAULT_OPUS_INPUT_PER_MTOK = 5.00
_DEFAULT_OPUS_OUTPUT_PER_MTOK = 25.00

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic | None:
    global _client
    if _client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            return None
        _client = AsyncAnthropic(api_key=key)
    return _client


def claude_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _price_per_mtok(env_key: str, default: float) -> float:
    raw = os.getenv(env_key)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def claude_opus_price_source() -> dict:
    return {
        "input_usd_per_mtok": _price_per_mtok("CLAUDE_OPUS_INPUT_PRICE_PER_MTOK", _DEFAULT_OPUS_INPUT_PER_MTOK),
        "output_usd_per_mtok": _price_per_mtok("CLAUDE_OPUS_OUTPUT_PRICE_PER_MTOK", _DEFAULT_OPUS_OUTPUT_PER_MTOK),
        "source": "claude-opus-4-8 list price (override via env for contracted rate)",
    }


def estimate_claude_cost_micros(input_tokens: int | None, output_tokens: int | None) -> int | None:
    """Mirrors services.telemetry.estimate_gemini_cost_micros: NULL only when both
    token counts are missing, so the ledger never records a fabricated zero."""
    if input_tokens is None and output_tokens is None:
        return None
    in_rate = _price_per_mtok("CLAUDE_OPUS_INPUT_PRICE_PER_MTOK", _DEFAULT_OPUS_INPUT_PER_MTOK)
    out_rate = _price_per_mtok("CLAUDE_OPUS_OUTPUT_PRICE_PER_MTOK", _DEFAULT_OPUS_OUTPUT_PER_MTOK)
    cost_usd = (int(input_tokens or 0) / 1_000_000) * in_rate + (int(output_tokens or 0) / 1_000_000) * out_rate
    return round(cost_usd * 1_000_000)


async def tracked_claude_message(
    *, operation: str, system: str, user_prompt: str, max_tokens: int = 4096,
) -> str:
    """Call Claude Opus 4.8 (adaptive thinking) and persist measured usage.

    Raises RuntimeError if ANTHROPIC_API_KEY isn't configured — callers treat this
    the same as any other "not configured" integration in this codebase (Stripe,
    Google sign-in): skip and log, never crash the caller. Raises ValueError if
    Claude returns no text. Never fabricates a result on failure.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    started = time.perf_counter()
    try:
        response = await client.messages.create(
            model=CLAUDE_OPUS_MODEL,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:
        await record_usage_event(
            operation=operation, provider="anthropic_claude", model=CLAUDE_OPUS_MODEL,
            success=False, latency_ms=(time.perf_counter() - started) * 1000,
            error_code=type(exc).__name__,
        )
        raise

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    usage = response.usage
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    stop_reason = getattr(response, "stop_reason", None)
    # A truncated turn (adaptive thinking ate the budget before the answer finished)
    # is a failure, never a partial narration silently stored and later injected
    # into live grading — same guard services.claude_scoring.py applies to Sonnet 5.
    truncated = stop_reason == "max_tokens"
    await record_usage_event(
        operation=operation, provider="anthropic_claude", model=CLAUDE_OPUS_MODEL,
        success=bool(text) and not truncated, latency_ms=(time.perf_counter() - started) * 1000,
        input_tokens=input_tokens, output_tokens=output_tokens,
        estimated_cost_micros=estimate_claude_cost_micros(input_tokens, output_tokens),
        error_code="truncated_max_tokens" if truncated else (None if text else "empty_response"),
    )
    if truncated:
        raise ValueError(f"Claude response truncated at max_tokens for operation={operation}")
    if not text:
        raise ValueError(f"Claude returned an empty response for operation={operation}")
    return text
