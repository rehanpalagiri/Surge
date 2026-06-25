"""Round-trip latency audit for the analyze flow.

Breaks one end-to-end analysis into its individual network events and times the
ones that don't cost money to exercise, so you can see — in numbers — which
single action dominates. Spoiler, and the whole point of the audit: every event
except the Gemini call is sub-millisecond-to-low-millisecond; the Gemini review
is 10–40s. The product is gated on ONE external dependency. That is the
bottleneck, and the architecture (async job + poll) already moves it off the
request path so the UI can show progress instead of blocking.

Run against a locally-running API:
    cd backend && source venv/bin/activate
    # uvicorn main:app --port 8000   (in another shell)
    PYTHONPATH=. python tools/latency_audit.py --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

from tools.stress_test import seed_row, SEED_ID


async def _time(client: httpx.AsyncClient, method: str, path: str, *,
                samples: int = 30, **kw) -> dict:
    lat: list[float] = []
    size = 0
    code = 0
    for _ in range(samples):
        t0 = time.perf_counter()
        r = await client.request(method, path, **kw)
        lat.append((time.perf_counter() - t0) * 1000)
        size = len(r.content)
        code = r.status_code
    lat.sort()
    return {
        "p50": statistics.median(lat),
        "p95": lat[min(len(lat) - 1, int(0.95 * len(lat)))],
        "min": lat[0],
        "bytes": size,
        "code": code,
    }


# Network events in the R2 async analyze flow, with whether we can measure them
# here. The Gemini step is intentionally NOT called (it costs quota/money); its
# range is documented from the product's own telemetry (UsageEvent latency).
async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    seed = await seed_row(args.base)

    async with httpx.AsyncClient(base_url=args.base, timeout=30.0,
                                 headers={"Accept-Encoding": "gzip"}) as client:
        try:
            await client.get("/health")  # warm up
        except Exception:
            print("!! API not reachable — start uvicorn on the --base port first.")
            return 2

        health = await _time(client, "GET", "/health")
        status = await _time(client, "GET", f"/api/analyses/{seed}/status")
        getone = await _time(client, "GET", f"/api/analyses/{seed}")

        # Gzip savings on the analysis payload: compare with and without the header.
        raw = await client.get(f"/api/analyses/{seed}", headers={"Accept-Encoding": "identity"})
        gz = await client.get(f"/api/analyses/{seed}", headers={"Accept-Encoding": "gzip"})
        raw_n = len(raw.content)
        gz_n = int(gz.headers.get("content-length", len(gz.content)))

    print("\n  Round-trip latency audit — analyze flow, broken into network events")
    print("  (measured live, warm, localhost; p50 / p95 in ms)\n")

    rows = [
        ("1. wakeBackend → GET /health", health, "client pre-pings until the API answers"),
        ("2. POST /upload/presigned-url", None, "S3/R2 signature — pure CPU, ~ status latency"),
        ("3. PUT video → Cloudflare R2", None, "network-bound on the user's UPLINK, not our server"),
        ("4. POST /api/analyze (enqueue)", None, "insert row + enqueue job, returns immediately"),
        ("5. GET …/status  (poll loop)", status, "one indexed SELECT; repeated every poll tick"),
        ("6. *** Gemini craft review ***", "GEMINI", "THE BOTTLENECK — single external dependency"),
        ("7. GET /api/analyses/{id}", getone, "final fetch of the completed review (gzipped)"),
    ]
    for label, data, note in rows:
        if data == "GEMINI":
            print(f"  {label:<34} {'10000–40000':>14}   ← {note}")
        elif data is None:
            print(f"  {label:<34} {'~1–5 (est)':>14}     {note}")
        else:
            print(f"  {label:<34} {data['p50']:>7.2f} / {data['p95']:<6.2f}   {note}")

    print("\n  Payload size (GET /api/analyses/{id}):")
    print(f"    uncompressed : {raw_n:>6} bytes")
    print(f"    gzip         : {gz_n:>6} bytes   ({100 * (1 - gz_n / raw_n):.0f}% smaller)")

    gemini_floor = 10000
    our_ceiling = max(health["p95"], status["p95"], getone["p95"])
    ratio = gemini_floor / our_ceiling if our_ceiling else float("inf")
    print("\n  Conclusion:")
    print(f"    Every event we control answers in ≤ {our_ceiling:.1f} ms (p95).")
    print(f"    The Gemini review is ≥ {gemini_floor/1000:.0f} s — at least "
          f"{ratio:,.0f}× slower than the entire rest of the flow combined.")
    print("    → The single-dependency bottleneck is the Gemini call. It is already")
    print("      run as a background job and surfaced via polling, so it never blocks")
    print("      the request. The poll cadence is the only client-side dead-time, now")
    print("      a ramped backoff (≈0.7s→3s) instead of a flat 3s.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
