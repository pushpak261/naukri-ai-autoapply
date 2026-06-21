"""
Tests for the GeminiProvider's error classification.

These specifically guard against regressions in distinguishing a daily
quota exhaustion (not worth retrying) from a transient rate limit or other
API error (worth retrying / different handling).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import errors as genai_errors

from src.ai.providers.gemini import GeminiProvider
from src.core.exceptions import LLMAPIError, LLMQuotaExceededError

# The exact error payload shape Gemini's free tier returns when the daily
# request quota for a model is exhausted (taken from a real production log).
DAILY_QUOTA_PAYLOAD = {
    "error": {
        "code": 429,
        "message": "You exceeded your current quota...",
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {"@type": "type.googleapis.com/google.rpc.Help", "links": []},
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaMetric": (
                            "generativelanguage.googleapis.com/"
                            "generate_content_free_tier_requests"
                        ),
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                        "quotaDimensions": {"location": "global", "model": "gemini-2.5-flash"},
                        "quotaValue": "20",
                    }
                ],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "13s"},
        ],
    }
}

# A per-minute rate-limit violation looks the same except for the quotaId.
PER_MINUTE_PAYLOAD = {
    "error": {
        "code": 429,
        "message": "You exceeded your current quota...",
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
                        "quotaValue": "15",
                    }
                ],
            },
        ],
    }
}


def _provider_with_error(error: Exception) -> GeminiProvider:
    provider = GeminiProvider(api_key="fake-key")
    provider._client = MagicMock()
    provider._client.aio.models.generate_content = AsyncMock(side_effect=error)
    return provider


class TestGeminiQuotaClassification:
    @pytest.mark.asyncio
    async def test_daily_quota_exhaustion_is_classified_correctly(self):
        err = genai_errors.ClientError(code=429, response_json=DAILY_QUOTA_PAYLOAD)
        provider = _provider_with_error(err)

        with pytest.raises(LLMQuotaExceededError) as exc_info:
            await provider.generate_content("test prompt")

        assert exc_info.value.is_daily_quota is True
        assert "daily" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_per_minute_rate_limit_is_not_flagged_as_daily(self):
        err = genai_errors.ClientError(code=429, response_json=PER_MINUTE_PAYLOAD)
        provider = _provider_with_error(err)

        with pytest.raises(LLMQuotaExceededError) as exc_info:
            await provider.generate_content("test prompt")

        assert exc_info.value.is_daily_quota is False

    @pytest.mark.asyncio
    async def test_non_429_api_error_raises_generic_llm_api_error(self):
        err = genai_errors.ServerError(code=500, response_json={"error": {"message": "oops"}})
        provider = _provider_with_error(err)

        with pytest.raises(LLMAPIError) as exc_info:
            await provider.generate_content("test prompt")

        assert not isinstance(exc_info.value, LLMQuotaExceededError)

    @pytest.mark.asyncio
    async def test_none_response_text_raises_clear_error(self):
        provider = GeminiProvider(api_key="fake-key")
        provider._client = MagicMock()
        fake_response = MagicMock()
        fake_response.text = None
        fake_response.candidates = []
        provider._client.aio.models.generate_content = AsyncMock(return_value=fake_response)

        with pytest.raises(LLMAPIError) as exc_info:
            await provider.generate_content("test prompt")

        assert (
            "safety filters" in str(exc_info.value).lower()
            or "no text" in str(exc_info.value).lower()
        )
