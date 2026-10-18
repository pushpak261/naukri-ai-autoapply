"""Career artifacts use real workspace evidence and never execute applications."""
# ruff: noqa: F811
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from api.deps import state
from src.naukri_agent.ai.llm_provider import GeminiProvider
from tests.test_dashboard_features import dashboard  # noqa: F401
from tests.test_dashboard_users import register_client


def response(kind='application'):
    return {'title': 'Role preparation', 'summary': 'Prepare evidence of Python work.',
            'sections': [{'heading': 'Profile summary', 'content': 'Python skills are included in the resume.',
                          'evidence': [{'source': 'resume', 'job_id': None, 'quote': 'Python'}]}],
            'questions': [{'question': f'How did you use Python in project {i}?', 'looking_for': 'Explain your own contribution and result.'} for i in range(4)] if kind == 'interview' else [],
            'daily_plan': [{'day': i, 'action': 'Review a saved role and prepare evidence.', 'rationale': 'Connect Python experience to actual requirements.'} for i in range(1, 8)] if kind == 'strategy' else [],
            'missing_information': ['Confirm project outcomes.']}


async def prepare(client):
    await client.put('/api/config', json={'gemini_api_key': 'fixture-only-key', 'use_gemini': True})
    await client.put('/api/resume/profile', json={'name': 'Test Candidate', 'skills': ['Python'], 'summary': 'Built Python services.'})
    result = await client.post('/api/import/full', json={'data': {'jobs': [{'id': 700, 'naukri_job_id': 'studio-test', 'title': 'Backend Engineer',
        'company': 'Test employer', 'url': 'https://example.invalid/job', 'skills': 'Python', 'description': 'Build Python services',
        'scraped_at': datetime.now(UTC).isoformat()}]}})
    assert result.status_code == 200
    return (await client.get('/api/jobs')).json()['items'][0]['id']


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['application', 'interview', 'strategy'])
async def test_generate_persists_evidence_and_history(dashboard, monkeypatch, kind):
    job_id = await prepare(dashboard)
    generate = AsyncMock(return_value=json.dumps(response(kind)))
    monkeypatch.setattr(GeminiProvider, 'generate_content', generate)
    result = await dashboard.post('/api/career-studio/generate', json={'kind': kind, 'job_id': job_id})
    assert result.status_code == 200, result.text
    item = result.json()
    assert item['sections'][0]['evidence'][0]['quote'] == 'Python'
    assert 'fixture-only-key' not in generate.await_args.args[0]
    history = (await dashboard.get('/api/career-studio/artifacts')).json()['items']
    assert history[0]['id'] == item['id']
    saved = (await dashboard.get('/api/career-studio/artifacts/' + item['id'])).json()
    assert '_resume_evidence' not in saved
    assert saved['kind'] == kind
    assert (await dashboard.get('/api/applications')).json()['total'] == 0


@pytest.mark.asyncio
async def test_unsupported_quotes_and_incomplete_interviews_are_not_saved(dashboard, monkeypatch):
    job_id = await prepare(dashboard)
    item = response()
    item['sections'][0]['evidence'][0]['quote'] = 'An invented qualification'
    monkeypatch.setattr(GeminiProvider, 'generate_content', AsyncMock(return_value=json.dumps(item)))
    result = await dashboard.post('/api/career-studio/generate', json={'kind':'application','job_id':job_id})
    assert result.status_code == 503
    assert (await dashboard.get('/api/career-studio/artifacts')).json()['items'] == []
    monkeypatch.setattr(GeminiProvider, 'generate_content', AsyncMock(return_value=json.dumps(response())))
    assert (await dashboard.post('/api/career-studio/generate', json={'kind':'interview','job_id':job_id})).status_code == 503


@pytest.mark.asyncio
async def test_preflight_and_provider_errors_are_visible(dashboard, monkeypatch):
    assert (await dashboard.post('/api/career-studio/generate', json={'kind':'strategy'})).status_code == 422
    job_id = await prepare(dashboard)
    assert (await dashboard.post('/api/career-studio/generate', json={'kind':'application'})).status_code == 422
    assert (await dashboard.post('/api/career-studio/generate', json={'kind':'interview','job_id':99999})).status_code == 404
    monkeypatch.setattr(GeminiProvider, 'generate_content', AsyncMock(side_effect=RuntimeError('fixture-only-key')))
    result = await dashboard.post('/api/career-studio/generate', json={'kind':'application','job_id':job_id})
    assert result.status_code == 503 and 'fixture-only-key' not in result.text


@pytest.mark.asyncio
async def test_interview_feedback_uses_saved_question_and_private_snapshot(dashboard, monkeypatch):
    job_id = await prepare(dashboard)
    monkeypatch.setattr(GeminiProvider, 'generate_content', AsyncMock(return_value=json.dumps(response('interview'))))
    artifact = (await dashboard.post('/api/career-studio/generate', json={'kind':'interview','job_id':job_id})).json()
    generate = AsyncMock(return_value=json.dumps({'assessment':'Give a more specific result.', 'strengths':['Clear Python context.'],
        'improvements':['Explain your own actions.'], 'follow_up_question':'What did you learn from that work?'}))
    monkeypatch.setattr(GeminiProvider, 'generate_content', generate)
    route = '/api/career-studio/artifacts/' + artifact['id'] + '/practice'
    result = await dashboard.post(route, json={'question_index':0,'answer':'I built a Python service and tested its behavior.'})
    assert result.status_code == 200, result.text
    assert 'project 0' in generate.await_args.args[0]
    assert (await dashboard.post(route, json={'question_index':5,'answer':'This is a sufficiently detailed answer.'})).status_code == 422
    assert (await dashboard.post(route, json={'question_index':0,'answer':' '*25})).status_code == 422


@pytest.mark.asyncio
async def test_artifacts_are_isolated_by_signed_in_account(dashboard, monkeypatch):
    job_id = await prepare(dashboard)
    monkeypatch.setattr(GeminiProvider, 'generate_content', AsyncMock(return_value=json.dumps(response())))
    item = (await dashboard.post('/api/career-studio/generate', json={'kind':'application','job_id':job_id})).json()
    async with register_client('studio-private@example.invalid') as other:
        assert (await other.get('/api/career-studio/artifacts')).json()['items'] == []
        assert (await other.get('/api/career-studio/artifacts/' + item['id'])).status_code == 404
    dashboard.headers.pop('Authorization')
    assert (await dashboard.get('/api/career-studio/artifacts')).status_code == 401


def test_artifact_paths_reject_traversal():
    from fastapi import HTTPException
    from api.routes.career_studio import artifact_path
    with pytest.raises(HTTPException):
        artifact_path('../../resume_profile')
