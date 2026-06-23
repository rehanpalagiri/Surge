"""Best-effort provider usage accounting.

Costs remain NULL until verified pricing is configured. Recording measured units
without inventing prices lets finance calculations be reproduced later.
"""
from __future__ import annotations

import logging
import time

from database import AsyncSessionLocal
from models import UsageEvent

log = logging.getLogger("usage_telemetry")


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
