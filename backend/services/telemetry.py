"""Best-effort provider usage accounting.

Cost is derived from measured token counts × the Gemini 2.5 Flash list price
(overridable per contracted rate via env). It stays NULL only when token counts
are unavailable, so a finance calc is never built on a fabricated zero.
"""
from __future__ import annotations

import logging
import os
import time

from database import AsyncSessionLocal
from models import UsageEvent

log = logging.getLogger("usage_telemetry")

# Gemini 2.5 Flash list price (USD per 1M tokens), used to convert measured tokens
# into a per-call cost. These are the public list rates — not a guess — and can be
# overridden to a contracted rate with GEMINI_FLASH_INPUT_PRICE_PER_MTOK /
# GEMINI_FLASH_OUTPUT_PRICE_PER_MTOK without a code change.
_DEFAULT_FLASH_INPUT_PER_MTOK = 0.30
_DEFAULT_FLASH_OUTPUT_PER_MTOK = 2.50

# Claude Sonnet 5 list price (USD per 1M tokens) for the scoring pass. Set to the
# CURRENT introductory rate ($2/$10, in effect through 2026-08-31) so the admin cost
# view and the rolling cost-window limiter reflect what Anthropic actually bills today.
# ⚠️ REVERTS to the standard $3/$15 on 2026-08-31 — on that date either bump these
# constants back to 3.00/15.00 or set the env overrides below, otherwise the estimate
# (and therefore the Pro cost-window cap) will UNDER-count real spend. Overridable per
# contracted rate with ANTHROPIC_SONNET_INPUT_PRICE_PER_MTOK / _OUTPUT_PRICE_PER_MTOK.
_DEFAULT_SONNET_INPUT_PER_MTOK = 2.00
_DEFAULT_SONNET_OUTPUT_PER_MTOK = 10.00


def _price_per_mtok(env_key: str, default: float) -> float:
    raw = os.getenv(env_key)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def gemini_price_source() -> dict:
    """The pricing actually in effect, for transparency in the admin cost view."""
    return {
        "input_usd_per_mtok": _price_per_mtok("GEMINI_FLASH_INPUT_PRICE_PER_MTOK", _DEFAULT_FLASH_INPUT_PER_MTOK),
        "output_usd_per_mtok": _price_per_mtok("GEMINI_FLASH_OUTPUT_PRICE_PER_MTOK", _DEFAULT_FLASH_OUTPUT_PER_MTOK),
        "source": "gemini-2.5-flash list price (override via env for contracted rate)",
    }


def estimate_gemini_cost_micros(input_tokens: int | None, output_tokens: int | None) -> int | None:
    """Per-call cost in micro-USD from token counts × list price. Returns None when
    BOTH token counts are missing, so the ledger stays honestly NULL rather than
    recording a fabricated 0."""
    if input_tokens is None and output_tokens is None:
        return None
    in_rate = _price_per_mtok("GEMINI_FLASH_INPUT_PRICE_PER_MTOK", _DEFAULT_FLASH_INPUT_PER_MTOK)
    out_rate = _price_per_mtok("GEMINI_FLASH_OUTPUT_PRICE_PER_MTOK", _DEFAULT_FLASH_OUTPUT_PER_MTOK)
    cost_usd = (int(input_tokens or 0) / 1_000_000) * in_rate + (int(output_tokens or 0) / 1_000_000) * out_rate
    return round(cost_usd * 1_000_000)


def anthropic_price_source() -> dict:
    """The Claude scoring-pass pricing actually in effect, for the admin cost view."""
    return {
        "input_usd_per_mtok": _price_per_mtok("ANTHROPIC_SONNET_INPUT_PRICE_PER_MTOK", _DEFAULT_SONNET_INPUT_PER_MTOK),
        "output_usd_per_mtok": _price_per_mtok("ANTHROPIC_SONNET_OUTPUT_PRICE_PER_MTOK", _DEFAULT_SONNET_OUTPUT_PER_MTOK),
        "source": "claude-sonnet-5 standard list price (override via env for contracted rate)",
    }


def estimate_anthropic_cost_micros(input_tokens: int | None, output_tokens: int | None) -> int | None:
    """Per-call cost in micro-USD for the Claude scoring pass, from token counts ×
    list price. Same honesty contract as the Gemini estimator: None when BOTH counts
    are missing, never a fabricated 0. Thinking tokens are billed as output tokens by
    Anthropic and are already folded into ``output_tokens`` by the SDK usage block."""
    if input_tokens is None and output_tokens is None:
        return None
    in_rate = _price_per_mtok("ANTHROPIC_SONNET_INPUT_PRICE_PER_MTOK", _DEFAULT_SONNET_INPUT_PER_MTOK)
    out_rate = _price_per_mtok("ANTHROPIC_SONNET_OUTPUT_PRICE_PER_MTOK", _DEFAULT_SONNET_OUTPUT_PER_MTOK)
    cost_usd = (int(input_tokens or 0) / 1_000_000) * in_rate + (int(output_tokens or 0) / 1_000_000) * out_rate
    return round(cost_usd * 1_000_000)


def response_token_usage(response) -> tuple[int | None, int | None]:
    try:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return None, None
        input_tokens = getattr(usage, "prompt_token_count", None)
        output_tokens = getattr(usage, "candidates_token_count", None)
        return input_tokens, output_tokens
    except Exception:
        return None, None


def response_text_bytes(response) -> int | None:
    """Best-effort UTF-8 byte length of the response text.

    `response.text` is a property that can raise (e.g. blocked/empty candidates)
    rather than return None. Measuring output size must never turn a successful
    provider call into a failure, so any error here yields None.
    """
    try:
        text = getattr(response, "text", None)
    except Exception:
        return None
    if not text:
        return None
    return len(text.encode("utf-8"))


async def record_usage_event(
    *,
    operation: str,
    provider: str,
    success: bool,
    latency_ms: int,
    analysis_id: int | None = None,
    model: str | None = None,
    model_version: str | None = None,
    input_bytes: int | None = None,
    output_bytes: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost_micros: int | None = None,
    error_code: str | None = None,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            db.add(UsageEvent(
                analysis_id=analysis_id,
                operation=operation,
                provider=provider,
                model=model,
                model_version=model_version,
                success=success,
                latency_ms=max(0, round(latency_ms)),
                input_bytes=input_bytes,
                output_bytes=output_bytes,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_micros=estimated_cost_micros,
                error_code=(error_code or "")[:120] or None,
            ))
            await db.commit()
    except Exception as exc:  # telemetry must never fail the user request
        log.warning("usage event dropped (%s/%s): %s", provider, operation, exc)


async def tracked_generate_content(
    client,
    *,
    operation: str,
    model: str,
    contents,
    config,
    analysis_id: int | None = None,
    input_bytes: int | None = None,
):
    """Call Gemini and persist measured usage without embedding a price guess."""
    started = time.perf_counter()
    try:
        response = await client.aio.models.generate_content(
            model=model, contents=contents, config=config
        )
        input_tokens, output_tokens = response_token_usage(response)
        await record_usage_event(
            operation=operation,
            provider="google_gemini",
            model=model,
            analysis_id=analysis_id,
            success=True,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_bytes=input_bytes,
            output_bytes=response_text_bytes(response),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_micros=estimate_gemini_cost_micros(input_tokens, output_tokens),
        )
        return response
    except Exception as exc:
        await record_usage_event(
            operation=operation,
            provider="google_gemini",
            model=model,
            analysis_id=analysis_id,
            success=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_bytes=input_bytes,
            error_code=type(exc).__name__,
        )
        raise
