"""Grounding, failure handling and settings propagation for dashboard Gemini advice."""
# ruff: noqa: F811
import json
from unittest.mock import AsyncMock

import pytest

from tests.test_dashboard_features import dashboard  # noqa: F401
from api.deps import state
from src.naukri_agent.ai.llm_provider import GeminiProvider


@pytest.mark.asyncio
async def test_advice_requires_enabled_key_and_evidence(dashboard):
    assert (await dashboard.post('/api/ai/advice', json={'feature': 'resume'})).status_code == 422
    await dashboard.put('/api/config', json={'gemini_api_key': 'fixture-secret', 'use_gemini': True})
    assert (await dashboard.post('/api/ai/advice', json={'feature': 'resume'})).status_code == 422
    assert (await dashboard.post('/api/ai/advice', json={'feature': 'unknown'})).status_code == 422
    assert (await dashboard.post('/api/ai/advice', json={'feature': 'jobs', 'job_id': 999})).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('feature', ['overview', 'jobs', 'applications', 'copilot', 'skills', 'market', 'scam', 'resume', 'agent', 'analytics'])
async def test_all_advice_features_use_private_grounded_context(dashboard, monkeypatch, feature):
    await dashboard.put('/api/config', json={'gemini_api_key': 'fixture-secret', 'use_gemini': True})
    (state.settings.project_root / 'resume_profile.json').write_text(json.dumps({'skills': ['Python'], 'email': 'private@example.invalid', 'raw_text': 'private raw text'}))
    generate = AsyncMock(return_value=json.dumps({'summary': 'Python is present.', 'recommendations': ['Prepare a real project example.'], 'cautions': ['No listings available.']}))
    monkeypatch.setattr(GeminiProvider, 'generate_content', generate)
    response = await dashboard.post('/api/ai/advice', json={'feature': feature})
    assert response.status_code == 200, response.text
    prompt = generate.await_args.args[0]
    assert 'Python' in prompt
    assert 'private@example.invalid' not in prompt
    assert 'private raw text' not in prompt
    assert 'fixture-secret' not in prompt
    assert response.json()['feature'] == feature
    assert response.json()['jobs_reviewed'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('output', ['not-json', '{}', '{"summary":"ok","recommendations":[],"cautions":[]}'])
async def test_invalid_advice_is_a_visible_failure(dashboard, monkeypatch, output):
    await dashboard.put('/api/config', json={'gemini_api_key': 'fixture-secret', 'use_gemini': True})
    (state.settings.project_root / 'resume_profile.json').write_text('{"skills":["Python"]}')
    monkeypatch.setattr(GeminiProvider, 'generate_content', AsyncMock(return_value=output))
    response = await dashboard.post('/api/ai/advice', json={'feature': 'skills'})
    assert response.status_code == 503
    assert 'fixture-secret' not in response.text


def test_linkedin_cache_changes_when_preferences_or_evidence_change(tmp_path):
    from src.linked_agent.ai.job_matcher import LinkedInJobMatcher
    from src.linked_agent.config.settings import Settings
    from src.linked_agent.models.entities import Job, ResumeProfile
    settings = Settings(project_root=tmp_path)
    matcher = LinkedInJobMatcher(AsyncMock(), settings)
    resume, job = ResumeProfile(skills=['Python']), Job(linkedin_job_id='fixture', title='Developer', company='Example', url='https://example.invalid/job')
    initial = matcher._cache_key(resume, job)
    settings.ai.use_gemini = not settings.ai.use_gemini
    assert matcher._cache_key(resume, job) != initial
    second = matcher._cache_key(resume, job)
    job.description = 'New requirements'
    assert matcher._cache_key(resume, job) != second


def test_linkedin_invalid_ai_never_falls_back_to_auto_apply(tmp_path):
    from src.linked_agent.ai.job_matcher import LinkedInJobMatcher
    from src.linked_agent.config.settings import Settings
    from src.linked_agent.models.entities import Job
    from src.linked_agent.utils.exceptions import LLMAPIError
    matcher = LinkedInJobMatcher(AsyncMock(), Settings(project_root=tmp_path))
    for response in ['{}', '{"match_score":101}', 'invalid']:
        with pytest.raises(LLMAPIError):
            matcher._parse_response(response, Job(linkedin_job_id='fixture', title='Developer', company='Example', url='https://example.invalid/job'))
