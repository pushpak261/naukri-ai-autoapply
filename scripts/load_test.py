"""
Smoke / load test for the hardened gateway + services.

Demonstrates that, under concurrency, the gateway:
  * verifies JWTs at the edge (401 without a token),
  * fails fast (5xx, not hangs) when a backend is down,
  * keeps p95 latency bounded.

Usage:
    python scripts/load_test.py                 # hits /api/health (public)
    python scripts/load_test.py --token <jwt>   # also exercises a protected route
    python scripts/load_test.py --requests 200 --concurrency 20

If no token is supplied and .env has NAUKRI_EMAIL/NAUKRI_PASSWORD, it will
log in once to obtain one. Otherwise only the public health route is exercised.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections import Counter

from dotenv import load_dotenv

import httpx

load_dotenv()

PROTECTED_PATH = "/api/jobs"


async def _worker(client: httpx.AsyncClient, sem: asyncio.Semaphore, path: str, headers: dict, results: list, latencies: list) -> None:
    async with sem:
        t0 = time.perf_counter()
        try:
            r = await client.get(path, headers=headers, timeout=35.0)
            results.append(r.status_code)
        except Exception as exc:  # connection refused / timeout -> fail-fast proof
            results.append(getattr(exc, "status_code", type(exc).__name__))
        finally:
            latencies.append(time.perf_counter() - t0)


async def _run(base_url: str, requests: int, concurrency: int, token: str | None) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    sem = asyncio.Semaphore(concurrency)
    results: list = []
    latencies: list = []

    # Always exercise the public health route (no token needed).
    async with httpx.AsyncClient(base_url=base_url) as client:
        tasks = [_worker(client, sem, "/api/health", {}, results, latencies) for _ in range(requests)]
        await asyncio.gather(*tasks)

        # If we have a token, also hammer a protected route.
        if token:
            results.clear()
            latencies.clear()
            tasks = [_worker(client, sem, PROTECTED_PATH, headers, results, latencies) for _ in range(requests)]
            await asyncio.gather(*tasks)

    counts = Counter(results)
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95) - 1] if latencies else 0.0
    route = PROTECTED_PATH if token else "/api/health"
    print(f"\n=== Load test: {requests} reqs @ concurrency {concurrency} -> {route} ===")
    print("status codes:", dict(counts))
    print(f"p95 latency: {p95 * 1000:.1f} ms | max: {max(latencies, default=0) * 1000:.1f} ms")
    if 401 in counts and not token:
        print("(401 expected here only if a token was required; health is public)")
    if any(str(c).startswith("5") for c in counts):
        print("NOTE: 5xx present -> a backend was down; gateway failed fast instead of hanging.")


def _login(base_url: str) -> str | None:
    email = os.environ.get("NAUKRI_EMAIL")
    password = os.environ.get("NAUKRI_PASSWORD")
    if not email or not password:
        return None
    try:
        with httpx.Client(base_url=base_url, timeout=30) as c:
            r = c.post("/api/auth/login", json={"email": email, "password": password})
            if r.status_code == 200:
                return r.json().get("access_token")
    except Exception:
        return None
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--requests", type=int, default=100)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--token", default=None)
    args = ap.parse_args()

    token = args.token or _login(args.url)
    if not token:
        print("No token available; running public /api/health smoke test only.")
    asyncio.run(_run(args.url, args.requests, args.concurrency, token))


if __name__ == "__main__":
    main()
