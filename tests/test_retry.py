"""
Tests for the async_retry utility decorator.
"""

import pytest
import asyncio
from src.utils.helpers import async_retry


class CustomException(Exception):
    pass


class OtherException(Exception):
    pass


@pytest.mark.asyncio
async def test_retry_success_on_first_try():
    """Verify that a successful async call executes exactly once."""
    call_count = 0

    @async_retry(max_attempts=3, delay_seconds=0.01)
    async def sample_func():
        nonlocal call_count
        call_count += 1
        return "success"

    result = await sample_func()
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_success_on_third_try():
    """Verify that retry runs until a success is returned (within max_attempts)."""
    call_count = 0

    @async_retry(max_attempts=3, delay_seconds=0.01, exceptions=(CustomException,))
    async def sample_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise CustomException("temporary error")
        return "success"

    result = await sample_func()
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausted():
    """Verify that the target exception is propagated once max_attempts are exhausted."""
    call_count = 0

    @async_retry(max_attempts=3, delay_seconds=0.01, exceptions=(CustomException,))
    async def sample_func():
        nonlocal call_count
        call_count += 1
        raise CustomException("persistent error")

    with pytest.raises(CustomException):
        await sample_func()

    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_ignores_non_targeted_exceptions():
    """Verify that non-targeted exceptions raise immediately without retrying."""
    call_count = 0

    @async_retry(max_attempts=3, delay_seconds=0.01, exceptions=(CustomException,))
    async def sample_func():
        nonlocal call_count
        call_count += 1
        raise OtherException("fatal error")

    with pytest.raises(OtherException):
        await sample_func()

    assert call_count == 1
