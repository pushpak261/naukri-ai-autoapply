"""
Google Gemini implementation of the ILLMProvider interface.
"""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from src.naukri_agent.core.exceptions import LLMAPIError, LLMQuotaExceededError
from src.naukri_agent.core.interfaces import ILLMProvider
from src.naukri_agent.utils.helpers import async_retry


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

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        """
        Initialize the Gemini provider.

        Args:
            api_key: The Google Gemini API key.
            model_name: The Gemini model to use.
        """
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

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
        Generate content from a prompt using Gemini asynchronously.

        Raises:
            LLMQuotaExceededError: on HTTP 429 / RESOURCE_EXHAUSTED. Check
                `.is_daily_quota` — if True, retrying within the same day
                will not help; callers should stop and surface guidance to
                the user rather than retry.
            LLMAPIError: for any other failure to generate content.
        """
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model_name,
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

            return response_text

        except genai_errors.APIError as e:
            if e.code == 429:
                is_daily = _is_daily_quota_violation(e)
                if is_daily:
                    raise LLMQuotaExceededError(
                        "Gemini free-tier DAILY request quota is exhausted for "
                        f"model '{self._model_name}'. Retrying now will not help — "
                        "the quota resets on a rolling daily window. Options: "
                        "(1) wait and try again later, (2) switch ai.model in "
                        "config.yaml to a different model (separate quota pool), "
                        "or (3) enable billing on the Google Cloud project tied "
                        "to this API key for much higher limits. See "
                        "https://ai.google.dev/gemini-api/docs/rate-limits",
                        is_daily_quota=True,
                    ) from e
                raise LLMQuotaExceededError(
                    f"Gemini rate limit hit (HTTP 429): {e.message or str(e)}",
                    is_daily_quota=False,
                ) from e
            raise LLMAPIError(f"Gemini API error ({e.code}): {e.message or str(e)}") from e
        except LLMAPIError:
            raise
        except Exception as e:
            raise LLMAPIError(f"Failed to generate content via Gemini API: {str(e)}") from e
