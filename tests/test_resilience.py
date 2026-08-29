import asyncio

import pytest

from libs.common.resilience import CircuitBreaker, CircuitOpen, RateLimiter, async_retry


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.2)
    calls = {"n": 0}

    async def boom():
        calls["n"] += 1
        raise ValueError("x")

    async def run():
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(boom)
        # Third call should be rejected by the open circuit.
        with pytest.raises(CircuitOpen):
            await cb.call(boom)
        assert cb.state == "open"

    asyncio.run(run())
    assert calls["n"] == 2  # rejected calls do not hit the dependency


def test_circuit_breaker_recovers():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.1)

    async def fail():
        raise ValueError()

    async def ok():
        return "ok"

    async def run():
        with pytest.raises(ValueError):
            await cb.call(fail)
        await asyncio.sleep(0.15)
        assert await cb.call(ok) == "ok"

    asyncio.run(run())


def test_rate_limiter_allows_up_to_capacity():
    rl = RateLimiter(rate=1000.0, capacity=1)

    async def run():
        assert await rl.consume("k") is True
        assert await rl.consume("k") is False  # capacity exhausted

    asyncio.run(run())


def test_async_retry_eventually_succeeds():
    n = {"n": 0}

    @async_retry(max_attempts=3, initial=0.01, max_wait=0.05, retry_on=lambda e: True)
    async def flaky():
        n["n"] += 1
        if n["n"] < 3:
            raise RuntimeError("boom")
        return "done"

    assert asyncio.run(flaky()) == "done"
    assert n["n"] == 3


def test_async_retry_gives_up():
    n = {"n": 0}

    @async_retry(max_attempts=2, initial=0.01, max_wait=0.05, retry_on=lambda e: True)
    async def always_fail():
        n["n"] += 1
        raise RuntimeError("boom")

    async def run():
        with pytest.raises(RuntimeError):
            await always_fail()

    asyncio.run(run())
    assert n["n"] == 2
