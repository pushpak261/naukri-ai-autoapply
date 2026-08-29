"""
Google Gemini implementation of the ILLMProvider interface.
"""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from src.naukri_agent.utils.exceptions import LLMAPIError, LLMQuotaExceededError
from src.naukri_agent.bot.interfaces import ILLMProvider
from src.naukri_agent.utils.helpers import async_retry
from src.naukri_agent.utils.logger import get_logger

logger = get_logger(__name__)


def _is_daily_quota_violation(error: genai_errors.APIError) -> bool:
    """
    Inspect a 429 APIError's structured details for a quota violation whose
    quotaId indicates a *daily* (not per-minute) limit. Gemini's free tier
    daily quota looks like 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'.
    Falls back to string-matching the raw error if the structure changes.
    """
    try:
        details = error.details or {}
        error_block = details.get("error", details) if isinstance(details, dict) else {}
        for detail in error_block.get("details", []):
            if not isinstance(detail, dict):
                continue
            for violation in detail.get("violations", []):
                quota_id = str(violation.get("quotaId", ""))
                if "PerDay" in quota_id:
                    return True
    except Exception:
        pass
    return "PerDay" in str(error)


class GeminiProvider(ILLMProvider):
    """
    LLM Provider implementation using Google Gemini.
    """

    def __init__(self, api_key: str | list[str], model_name: str = "gemini-2.0-flash") -> None:
        """
        Initialize the Gemini provider.

        Args:
            api_key: The Google Gemini API key.
            model_name: The Gemini model to use.
        """
        if isinstance(api_key, str):
            keys = [k.strip() for k in api_key.split(",") if k.strip()]
            self._api_key = keys[0] if keys else ""
        elif isinstance(api_key, list):
            self._api_key = api_key[0] if api_key else ""
        else:
            self._api_key = api_key

        self._model_name = model_name
        self._client: genai.Client | None = None
        from src.naukri_agent.utils.rate_limiter import TokenBucketRateLimiter

        # Initialize token bucket rate limiter: default 15 RPM for free tier (0.25 tokens/sec)
        self._rate_limiter = TokenBucketRateLimiter(capacity=15.0, refill_rate=15.0 / 60.0)

    def _get_client(self) -> genai.Client:
        """Lazy-initialize the genai.Client on demand."""
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "No API key was provided. Please configure GEMINI_API_KEY in your environment."
                )
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def set_model(self, model_name: str) -> None:
        """
        Dynamically switch the Gemini model.
        """
        self._model_name = model_name

    @async_retry(
        max_attempts=3,
        delay_seconds=2.0,
        backoff_factor=2.0,
        exceptions=(LLMAPIError,),
    )
    async def generate_content(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_output_tokens: int = 2048,
        response_mime_type: str = "text/plain",
        response_schema: Any = None,
    ) -> str:
        """
        Generate content from a prompt using Gemini asynchronously with automatic fallback models.
        """
        await self._rate_limiter.acquire(1.0)

        # Candidates to try if model name is rejected (e.g. 404 model deprecated)
        models_to_try = [self._model_name]
        for fallback in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash"]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error = None
        for current_model in models_to_try:
            try:
                response = await self._get_client().aio.models.generate_content(
                    model=current_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        response_mime_type=response_mime_type,
                        response_schema=response_schema,
                    ),
                )

                if response.text is None:
                    finish_reason = None
                    if response.candidates:
                        finish_reason = response.candidates[0].finish_reason
                    raise LLMAPIError(
                        "Gemini returned no text content "
                        f"(finish_reason={finish_reason!r}). This usually means the "
                        "request was blocked by safety filters or hit a token limit."
                    )

                response_text = response.text.strip()

                # Clean markdown code fences if JSON was requested
                if response_mime_type == "application/json" and response_text.startswith("```"):
                    lines = response_text.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    response_text = "\n".join(lines)

                self._model_name = current_model
                return response_text

            except genai_errors.APIError as e:
                if e.code == 429:
                    is_daily = _is_daily_quota_violation(e)
                    if is_daily:
                        raise LLMQuotaExceededError(
                            "Gemini free-tier DAILY request quota is exhausted for "
                            f"model '{current_model}'.",
                            is_daily_quota=True,
                        ) from e
                    raise LLMQuotaExceededError(
                        f"Gemini rate limit hit (HTTP 429): {e.message or str(e)}",
                        is_daily_quota=False,
                    ) from e
                if e.code == 404 or "no longer available" in str(e).lower() or "not found" in str(e).lower():
                    logger.warning(f"Model '{current_model}' unavailable ({e.message or str(e)}), trying next fallback...")
                    last_error = e
                    continue
                raise LLMAPIError(f"Gemini API error ({e.code}): {e.message or str(e)}") from e
            except LLMAPIError:
                raise
            except Exception as e:
                last_error = e
                break

        if last_error:
            raise LLMAPIError(f"Failed to generate content across available models: {last_error}")
        raise LLMAPIError("No response from Gemini API.")

