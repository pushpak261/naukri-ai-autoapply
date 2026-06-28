"""
Tests for Token Bucket Rate Limiter.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.naukri_agent.utils.rate_limiter import TokenBucketRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_pacing() -> None:
    # 2 tokens capacity, refills at 2 tokens per second (1 token every 0.5s)
    limiter = TokenBucketRateLimiter(capacity=2.0, refill_rate=2.0)

    start = time.monotonic()

    # Acquire 2 tokens immediately
    await limiter.acquire(1.0)
    await limiter.acquire(1.0)

    # Bucket is empty, acquiring another 1 token should block/sleep for ~0.5s
    await limiter.acquire(1.0)

    end = time.monotonic()
    duration = end - start

    assert duration >= 0.4  # Should sleep for about 0.5 seconds
