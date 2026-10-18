"""
LinkedIn-specific Gemini LLM provider.
Reuses the same Gemini API integration as the Naukri agent.
"""

from __future__ import annotations

import asyncio

from src.linked_agent.bot.interfaces import ILLMProvider
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


class GeminiProvider(ILLMProvider):
    """Google Gemini LLM provider for LinkedIn agent AI operations."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        self._api_key = api_key
        self._model_name = model_name

    def set_model(self, model_name: str) -> None:
        """Switch to a different model (e.g., fallback)."""
        self._model_name = model_name
        logger.info(f"Switched to model: {model_name}")

    async def generate_content(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_output_tokens: int = 2048,
        response_mime_type: str = "text/plain",
        response_schema: object | None = None,
    ) -> str:
        """Generate content using Google Gemini API with fallback support."""
        from google import genai

        from google.genai import types
        client = genai.Client(api_key=self._api_key, http_options=types.HttpOptions(timeout=90000))

        models_to_try = [self._model_name]
        for fallback in ["gemini-2.5-flash", "gemini-2.5-flash-lite"]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error = None
        for current_model in models_to_try:
            try:
                from libs.common.gemini_output import thinking_config, ensure_complete
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_schema=response_schema,
                    response_mime_type=response_mime_type if response_mime_type != "text/plain" else None,
                    thinking_config=thinking_config(current_model),
                )
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=current_model,
                    contents=prompt,
                    config=config,
                )

                ensure_complete(response)
                if response.text is None:
                    from src.linked_agent.utils.exceptions import LLMAPIError
                    finish_reason = None
                    if response.candidates:
                        finish_reason = response.candidates[0].finish_reason
                    raise LLMAPIError(
                        "Gemini returned no text content "
                        f"(finish_reason={finish_reason!r})."
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

            except Exception as e:
                error_str = str(e).lower()
                if "quota" in error_str or "429" in error_str:
                    from src.linked_agent.utils.exceptions import LLMQuotaExceededError
                    is_daily = any(marker in error_str for marker in ("daily", "per day", "perday"))
                    message = (
                        'Gemini daily request quota is exhausted. Wait for the quota reset or check your Gemini project billing and limits.'
                        if is_daily else
                        'Gemini request rate limit reached. Wait before retrying.'
                    )
                    raise LLMQuotaExceededError(
                        message,
                        is_daily_quota=is_daily,
                    ) from e
                if "404" in error_str or "no longer available" in error_str or "not found" in error_str:
                    logger.warning(f"Model '{current_model}' unavailable, trying fallback...")
                    last_error = e
                    continue
                from src.linked_agent.utils.exceptions import LLMAPIError
                raise LLMAPIError(f"Gemini API error: {e}") from e

        if last_error:
            from src.linked_agent.utils.exceptions import LLMAPIError
            raise LLMAPIError(f"Gemini API error: {last_error}")
        from src.linked_agent.utils.exceptions import LLMAPIError
        raise LLMAPIError("No response from Gemini API.")

