"""
Token Bucket Rate Limiter implementation for async request pacing.
"""

from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:
    """
    An asynchronous Token Bucket Rate Limiter.
    Manages a bucket of tokens that refill at a constant rate up to a capacity.
    """

    def __init__(self, capacity: float, refill_rate: float) -> None:
        """
        Initialize the rate limiter.

        Args:
            capacity: Maximum number of tokens the bucket can hold.
            refill_rate: Number of tokens added to the bucket per second.
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        """
        Acquire the specified number of tokens. Blocks/sleeps if insufficient tokens.

        Args:
            tokens: Number of tokens to acquire.
        """
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now

                # Refill bucket based on elapsed time
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # Calculate duration to wait for enough tokens
                needed = tokens - self.tokens
                sleep_duration = needed / self.refill_rate

            # Sleep outside of the lock context to allow other concurrent calls
            await asyncio.sleep(sleep_duration)
