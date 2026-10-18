from types import SimpleNamespace

import pytest

from libs.common.gemini_output import ensure_complete, thinking_config


def test_flash_reserves_output_for_json():
    assert thinking_config('gemini-2.5-flash').thinking_budget == 0
    assert thinking_config('gemini-2.5-flash-lite').thinking_budget == 0
    assert thinking_config('gemini-2.5-pro') is None
    assert thinking_config('gemini-3-flash') is None


def test_truncated_even_valid_looking_json_is_rejected():
    response = SimpleNamespace(text='{}', candidates=[SimpleNamespace(finish_reason='MAX_TOKENS')])
    with pytest.raises(ValueError, match='truncated'):
        ensure_complete(response)


def test_completed_response_is_accepted():
    ensure_complete(SimpleNamespace(candidates=[SimpleNamespace(finish_reason='STOP')]))


@pytest.mark.asyncio
async def test_linkedin_provider_applies_budget_and_rejects_partial_output(monkeypatch):
    from google import genai
    from src.linked_agent.ai.llm_provider import GeminiProvider
    from src.linked_agent.utils.exceptions import LLMAPIError

    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text='{"should_apply": true}', candidates=[SimpleNamespace(finish_reason='MAX_TOKENS')])

    monkeypatch.setattr(genai, 'Client', lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    with pytest.raises(LLMAPIError, match='truncated'):
        await GeminiProvider('test-key').generate_content('test', response_mime_type='application/json')
    assert calls[0]['config'].thinking_config.thinking_budget == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('detail,daily', [('GenerateRequestsPerDayPerProjectPerModel-FreeTier', True), ('requests per minute', False)])
async def test_linkedin_quota_classification_stops_without_model_fallback(monkeypatch, detail, daily):
    from google import genai
    from src.linked_agent.ai.llm_provider import GeminiProvider
    from src.linked_agent.utils.exceptions import LLMQuotaExceededError
    calls = []

    def generate(**kwargs):
        calls.append(kwargs['model'])
        raise RuntimeError('429 quota exceeded: ' + detail)

    monkeypatch.setattr(genai, 'Client', lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    with pytest.raises(LLMQuotaExceededError) as caught:
        await GeminiProvider('test-key').generate_content('test')
    assert caught.value.is_daily_quota is daily
    assert len(calls) == 1
    assert 'RuntimeError' not in str(caught.value)
