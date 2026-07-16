"""Load / stress test for the CraftLint API.

Fires a controlled number of concurrent requests at the read-path endpoints and
reports throughput, latency percentiles, and error rate at several concurrency
levels (1, 100, 1000 by default) — answering "is this bulletproof at 1 user, at
1000 users, at any time of day?".

It deliberately exercises only safe, idempotent GET endpoints:
    • GET /health                       — pure ASGI, no DB (raw server ceiling)
    • GET /api/analyses/{id}/status     — one indexed SELECT  (light DB read)
    • GET /api/analyses/{id}            — full locked payload  (DB + JSON + gzip)

It never touches Gemini or any paid third-party provider. Before the run it
seeds one realistic completed analysis row (idempotent) so the read endpoints
have a target.

Usage:
    cd backend && source venv/bin/activate
    # start the API in another shell:  uvicorn main:app --port 8000
    PYTHONPATH=. python tools/stress_test.py --base http://127.0.0.1:8000
    PYTHONPATH=. python tools/stress_test.py --levels 1,100,1000 --json report.json

Note: locally the DB is SQLite (single writer); production is Neon Postgres with
a real connection pool, so the DB-backed numbers here are a conservative floor.
The /health number (no DB) is representative of pure app-server throughput.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx

SEED_ID = 999_000_001  # high, fixed id unlikely to collide with real rows


# A realistically-sized craft-review payload so the GET /analyses/{id} response
# reflects production wire size (and exercises the new gzip middleware).
def _realistic_scores() -> dict:
    return {
        "hook_velocity": 7.5, "cut_frequency": 6.0, "text_scannability": 8.0,
        "curiosity_gap": 5.5, "audio_visual_sync": 7.0, "loop_seamlessness": 6.5,
        "verdict": "Solid craft",
        "analysis_summary": (
            "The opening frame establishes the subject quickly and the on-screen "
            "text is legible against the background. Pacing is consistent though a "
            "few mid-clip cuts linger longer than the surrounding rhythm. " * 4
        ),
        "strengths": [
            "Cold open lands the subject inside the first second.",
            "Captions are high-contrast and never collide with UI-safe zones.",
            "Audio beat changes are matched to visual cuts for most of the runtime.",
        ],
        "improvements": [
            "Tighten the two cuts around the midpoint to hold rhythm.",
            "The loop point has a visible jump — match first and last frames.",
        ],
        "improvement_plan": [
            {"area": "Hook", "priority": 1, "current_score": 7.5,
             "problem": "Hook is good but the payoff is implied, not shown.",
             "fix": "Show the end-state for ~0.5s before the reveal.",
             "pattern": "cold open"},
            {"area": "Pacing", "priority": 2, "current_score": 6.0,
             "problem": "Two mid-clip cuts run long relative to the set rhythm.",
             "fix": "Trim each by 4–6 frames to keep the cadence even.",
             "pattern": "rhythm match"},
            {"area": "Loop", "priority": 3, "current_score": 6.5,
             "problem": "First and last frames don't align, breaking the loop.",
             "fix": "Re-time the final beat so the last frame matches the first.",
             "pattern": "seamless loop"},
        ],
        "recommended_experiment": {
            "change": "Shorten the two long mid cuts by ~5 frames each.",
            "keep_constant": "Hook, caption, audio track, and post time.",
            "observe": "Compare completion-driven reach at the same 24h post age.",
        },
        "emotional_analysis": {
            "target_emotions": ["curiosity", "satisfaction"],
            "achieved_score": 7,
            "what_lands": "The setup creates a clear open question.",
            "what_misses": "The resolution is slightly rushed.",
            "how_to_amplify": ["Hold the reveal a beat longer."],
        },
        "caption_rewrite": "POV: you finally figured out the thing nobody explains →",
        "hook_rewrite": "Stop scrolling — here's the part they skip.",
        "craft_review_version": 2,
    }


async def seed_row(base: str) -> int:
    """Insert one completed, unclaimed analysis row directly via the app's DB.

    Idempotent: if SEED_ID already exists it's left as-is. Returns the id to hit.
    """
    # Imported lazily so the file still parses without app deps on the path.
    from database import AsyncSessionLocal
    from models import UserAnalysis
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(
            select(UserAnalysis.id).where(UserAnalysis.id == SEED_ID)
        )).first()
        if existing:
            return SEED_ID
        db.add(UserAnalysis(
            id=SEED_ID,
            user_id=None,  # unclaimed → GET returns the locked teaser, no auth needed
            platform="tiktok",
            filename="stresstest.mp4",
            project_name="Stress test fixture",
            niche="Lifestyle",
            canonical_niche="lifestyle",
            caption="stress test caption",
            scores_json=json.dumps(_realistic_scores()),
            verdict="Solid craft",
            mode="craft_review",
            status="complete",
        ))
        await db.commit()
    return SEED_ID


@dataclass
class Result:
    name: str
    concurrency: int
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    wall_seconds: float = 0.0

    @property
    def ok(self) -> int:
        return len(self.latencies_ms)

    def pct(self, p: float) -> float:
        if not self.latencies_ms:
            return float("nan")
        ordered = sorted(self.latencies_ms)
        k = max(0, min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1)))))
        return ordered[k]

    @property
    def rps(self) -> float:
        return self.ok / self.wall_seconds if self.wall_seconds else 0.0


async def run_scenario(client: httpx.AsyncClient, name: str, path: str,
                       total: int, concurrency: int) -> Result:
    res = Result(name=name, concurrency=concurrency)
    sem = asyncio.Semaphore(concurrency)

    async def one() -> None:
        async with sem:
            t0 = time.perf_counter()
            try:
                r = await client.get(path)
                dt = (time.perf_counter() - t0) * 1000
                if r.status_code < 500:
                    res.latencies_ms.append(dt)
                else:
                    res.errors += 1
            except Exception:
                res.errors += 1

    start = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(total)))
    res.wall_seconds = time.perf_counter() - start
    return res


def fmt_row(r: Result) -> str:
    return (
        f"  c={r.concurrency:<5} n={r.ok + r.errors:<6} "
        f"ok={r.ok:<6} err={r.errors:<4} "
        f"{r.rps:>8.0f} req/s   "
        f"p50={r.pct(50):>6.1f}  p95={r.pct(95):>7.1f}  "
        f"p99={r.pct(99):>7.1f}  max={r.pct(100):>7.1f} ms"
    )


async def main() -> int:
    ap = argparse.ArgumentParser(description="CraftLint API load test")
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--levels", default="1,100,1000",
                    help="comma-separated concurrency levels")
    ap.add_argument("--requests-per-conn", type=int, default=20,
                    help="requests per concurrent slot (total = level * this)")
    ap.add_argument("--max-total", type=int, default=8000,
                    help="hard cap on requests per scenario/level")
    ap.add_argument("--json", default="", help="optional path to write a JSON report")
    args = ap.parse_args()

    levels = [int(x) for x in args.levels.split(",") if x.strip()]

    try:
        seed_id = await seed_row(args.base)
    except Exception as exc:  # noqa: BLE001 — surface seeding problems plainly
        print(f"!! could not seed fixture row ({exc!r}). "
              f"Read-endpoint scenarios will report 404s.", file=sys.stderr)
        seed_id = SEED_ID

    scenarios = [
        ("health         (no DB)", "/health"),
        ("status         (1 SELECT)", f"/api/analyses/{seed_id}/status"),
        ("analysis JSON  (DB+gzip)", f"/api/analyses/{seed_id}"),
    ]

    # Generous connection pool so the client isn't the bottleneck at c=1000.
    limits = httpx.Limits(max_connections=max(levels) + 50,
                          max_keepalive_connections=max(levels) + 50)
    report: dict = {"base": args.base, "seed_id": seed_id, "scenarios": {}}

    print(f"\nCraftLint API stress test → {args.base}")
    print(f"levels={levels}  requests/conn={args.requests_per_conn}  "
          f"(capped at {args.max_total}/scenario-level)\n")

    async with httpx.AsyncClient(base_url=args.base, timeout=30.0,
                                 limits=limits, headers={"Accept-Encoding": "gzip"}) as client:
        # Warm up so first-call import/connection costs don't skew p50.
        try:
            await client.get("/health")
        except Exception:
            print("!! API not reachable — is uvicorn running on the --base port?",
                  file=sys.stderr)
            return 2

        for name, path in scenarios:
            print(name)
            report["scenarios"][name] = []
            for c in levels:
                total = min(args.max_total, c * args.requests_per_conn)
                r = await run_scenario(client, name, path, total, c)
                print(fmt_row(r))
                report["scenarios"][name].append({
                    "concurrency": c, "total": total, "ok": r.ok, "errors": r.errors,
                    "rps": round(r.rps, 1), "p50_ms": round(r.pct(50), 2),
                    "p95_ms": round(r.pct(95), 2), "p99_ms": round(r.pct(99), 2),
                    "max_ms": round(r.pct(100), 2),
                })
            print()

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"JSON report → {args.json}")

    # A simple pass/fail gate: zero 5xx/connection errors across every level.
    total_err = sum(s["errors"] for rows in report["scenarios"].values() for s in rows)
    verdict = "PASS — 0 errors across all levels" if total_err == 0 else f"FAIL — {total_err} errors"
    print(f"Verdict: {verdict}")
    return 0 if total_err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
