"""End-to-end identity and storage boundaries between two dashboard users."""
import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from tests.test_dashboard_features import dashboard  # noqa: F401
# The imported pytest fixture is intentionally shadowed by test parameters.
# ruff: noqa: F811
from api.deps import root_state


@asynccontextmanager
async def register_client(email):
    from api.main import app
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://testserver')
    result = await client.post('/api/auth/register', json={'email': email, 'password': 'Dummy-password-12345'})
    assert result.status_code == 200, result.text
    client.headers['Authorization'] = 'Bearer ' + result.json()['access_token']
    try:
        yield client
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_registration_creates_independent_identities_and_revokes_refresh(dashboard):
    from api import identity
    async with register_client('Alice@example.invalid') as alice:
        user = identity.find_user('alice@example.invalid')
        assert user['password_hash'] != 'Dummy-password-12345'
        assert user['is_operator'] == 0
        assert root_state.settings.naukri.email == 'operator@example.invalid'
        duplicate = await alice.post('/api/auth/register', json={'email': 'ALICE@example.invalid', 'password': 'Different-password-123'})
        assert duplicate.status_code == 409
        info = (await alice.get('/api/auth/me')).json()
        assert info['email'] == 'alice@example.invalid'
        assert info['naukri_configured'] is False
        original = alice.cookies.get('naukri_refresh_token')
        assert (await alice.post('/api/auth/refresh')).status_code == 200
        rotated = alice.cookies.get('naukri_refresh_token')
        assert rotated != original
        replay = await alice.post('/api/auth/refresh', headers={'Cookie': f'naukri_refresh_token={original}'})
        assert replay.status_code == 401
        # Re-login and then revoke that refresh session.
        login = await alice.post('/api/auth/login', json={'email': 'alice@example.invalid', 'password': 'Dummy-password-12345'})
        assert login.status_code == 200
        token = alice.cookies.get('naukri_refresh_token')
        assert (await alice.post('/api/auth/logout')).status_code == 200
        assert (await alice.post('/api/auth/refresh', headers={'Cookie': f'naukri_refresh_token={token}'})).status_code == 401


@pytest.mark.asyncio
async def test_users_cannot_read_or_mutate_each_others_records(dashboard):
    async with register_client('a@example.invalid') as a, register_client('b@example.invalid') as b:
        created = await a.post('/api/accounts', json={'email': 'platform-a@example.invalid', 'password': 'platform-password', 'name': 'Only A'})
        assert created.status_code == 200, created.text
        identifier = created.json()['account']['id']
        assert (await b.get('/api/accounts')).json()['items'] == []
        assert (await b.delete(f'/api/accounts/{identifier}')).status_code == 404
        assert all(item['email'] != 'platform-a@example.invalid' for item in (await dashboard.get('/api/accounts')).json()['items'])
        assert (await a.get('/api/logs/read', params={'log_path': str(root_state.settings.project_root / 'config.yaml')})).status_code == 400
        assert (await a.get('/api/logs/read', params={'log_path': '../../../../etc/passwd'})).status_code == 400
        assert (await a.put('/api/config', json={'search_keywords': ['Python A']})).status_code == 200
        assert (await b.put('/api/config', json={'search_keywords': ['Java B']})).status_code == 200
        pairs = await asyncio.gather(*[client.get('/api/config') for client in (a,b,a,b,a,b)])
        assert [r.json()['search']['keywords'] for r in pairs] == [['Python A'],['Java B']]*3
        assert all(not r.json()['ai']['has_api_key'] for r in pairs)
        assert (await a.put('/api/config/linkedin', json={'linkedin_email': 'a@platform.invalid'})).status_code == 200
        assert (await b.get('/api/config/linkedin')).json()['configured'] is False
        assert (await a.put('/api/config/linkedin', json={'resume_path': '/etc/passwd'})).status_code == 422
        # A's resume and exports must remain scoped even after B clears their data.
        assert (await a.put('/api/resume/profile', json={'name': 'Alice'})).status_code == 200
        assert (await a.get('/api/resume-profile')).json()['profile']['name'] == 'Alice'
        assert (await b.get('/api/resume-profile')).json()['profile'] is None
        assert (await b.delete('/api/data/clear-all')).status_code == 200
        assert len((await a.get('/api/accounts')).json()['items']) == 1
        assert (await b.get('/api/accounts')).json()['items'] == []
        assert (await b.get('/api/export/full')).json()['data']['jobs'] == []


@pytest.mark.asyncio
async def test_agent_environment_cannot_inherit_operator_credentials(dashboard, monkeypatch):
    from api import identity
    from api.deps import current_state
    from api.tenants import agent_environment, runtime_for
    async with register_client('runner@example.invalid') as client:
        runtime = await runtime_for(identity.find_user('runner@example.invalid'))
        monkeypatch.setenv('NAUKRI_EMAIL', 'operator-secret@example.invalid')
        monkeypatch.setenv('GEMINI_API_KEY', 'operator-ai-secret')
        token = current_state.set(runtime)
        try:
            env = agent_environment()
            assert 'NAUKRI_EMAIL' not in env
            assert 'GEMINI_API_KEY' not in env
            assert env['AGENT_WORKSPACE'] == str(runtime.settings.project_root)
            assert runtime.settings.db_path != root_state.settings.db_path
        finally:
            current_state.reset(token)
        assert (await client.get('/api/config')).json()['naukri']['has_password'] is False


@pytest.mark.asyncio
async def test_resume_paths_and_browser_preflight_are_scoped(dashboard):
    from api import identity
    from api.tenants import runtime_for
    async with register_client('paths@example.invalid') as user:
        runtime = await runtime_for(identity.find_user('paths@example.invalid'))
        runtime.settings.resume.path = 'data/resumes/own.pdf'
        other_file = root_state.settings.resumes_dir / 'operator.pdf'
        other_file.write_bytes(b'operator-only')
        result = await user.put('/api/resume/profile', json={'uploaded_file_path': str(other_file)})
        assert result.status_code == 400
        assert (await user.post('/api/agent/start?platform=naukri')).status_code == 422
        assert runtime.agent_process is None
        assert (await user.post('/api/agent/start?platform=linkedin')).status_code == 422
        forbidden = await user.get('/api/config', headers={'Origin': 'https://untrusted.example.invalid'})
        assert 'access-control-allow-origin' not in forbidden.headers


@pytest.mark.asyncio
async def test_new_accounts_use_their_resume_instead_of_legacy_java_filters(dashboard):
    from api import identity
    from api.tenants import runtime_for
    from src.naukri_agent.fake_job_detection.rules import TitleExclusionSpecification
    from tests.test_bot_agent_helpers import java_job, make_agent
    from src.naukri_agent.ai.job_matcher import JobMatcher
    from src.naukri_agent.models.entities import ResumeProfile
    from unittest.mock import AsyncMock
    import json
    async with register_client('python@example.invalid'):
        runtime = await runtime_for(identity.find_user('python@example.invalid'))
        settings = runtime.settings
        assert settings.exclusions.legacy_domain_filter is False
        job = java_job(title='Python Developer', skills='Python', description='Python API development', experience='3-5 Yrs')
        agent = make_agent(settings=settings)
        assert agent._passes_targeting(job)[0] is True
        assert not TitleExclusionSpecification([], False).is_satisfied_by(job)
        settings.ai.use_gemini = True
        provider = AsyncMock()
        provider.generate_content.return_value = json.dumps({'score':90,'should_apply':True,'matching_skills':['Python'],'missing_skills':[],'reasoning':'Python matches'})
        matcher = JobMatcher(provider, settings)
        result = await matcher.match(ResumeProfile(name='Python candidate', skills=['Python']), job)
        assert result.should_apply
        prompt = provider.generate_content.await_args.kwargs['prompt']
        assert 'Python candidate' in prompt
        assert 'primary stack is Java' not in prompt


@pytest.mark.asyncio
async def test_webhooks_reject_private_network_destinations(monkeypatch):
    from api.outbound import post_public_webhook
    import socket
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1',443))])
    with pytest.raises(ValueError, match='public IP'):
        await post_public_webhook('https://internal.example.invalid/test', '{}', {})


@pytest.mark.asyncio
async def test_browser_capacity_and_platform_password_storage(dashboard, monkeypatch):
    from unittest.mock import Mock
    from api import identity
    from api.tenants import runtime_for
    from api.agent_runtime import ensure_browser_capacity
    from fastapi import HTTPException
    from libs.common.security import decrypt_value
    from sqlalchemy import select
    from src.naukri_agent.models.db_schema import NaukriAccount

    async with register_client('capacity@example.invalid') as user:
        await user.post('/api/accounts', json={'email': 'platform@example.invalid', 'password': 'Dummy-platform-secret'})
        runtime = await runtime_for(identity.find_user('capacity@example.invalid'))
        async with runtime.db_manager.session_factory() as session:
            account = (await session.execute(select(NaukriAccount))).scalars().one()
            assert account.password != 'Dummy-platform-secret'
            assert decrypt_value(account.password) == 'Dummy-platform-secret'
        monkeypatch.setenv('MAX_ACTIVE_AGENTS', '1')
        process = Mock()
        process.poll.return_value = None
        monkeypatch.setattr(runtime, 'agent_process', process)
        with pytest.raises(HTTPException) as error:
            ensure_browser_capacity()
        assert error.value.status_code == 409
        monkeypatch.setattr(runtime, 'agent_process', None)
        ensure_browser_capacity()
