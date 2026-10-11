"""Dashboard API workflows against an isolated SQLite database and file store."""
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import pytest_asyncio
import yaml
from sqlalchemy import select

from api.deps import state
from src.naukri_agent.config import settings as settings_module
from src.naukri_agent.models.db_schema import Application, Job


@pytest_asyncio.fixture
async def dashboard(tmp_path, monkeypatch):
    from api.main import app
    config = {
        'project_root': str(tmp_path), 'data_dir': str(tmp_path / 'data'),
        'db_path': str(tmp_path / 'data' / 'naukri_agent.db'),
        'sessions_dir': str(tmp_path / 'data' / 'sessions'),
        'resumes_dir': str(tmp_path / 'data' / 'resumes'),
        'jwt_secret': 'isolated-test-signing-secret-at-least-32-bytes',
        'jwt_encryption_key': 'isolated-test-encryption-secret',
        'naukri': {'email': 'operator@example.invalid', 'password': 'test-password'},
        'ai': {'use_gemini': False},
        'application': {'dry_run': True, 'enable_project_indexer': False},
    }
    (tmp_path / 'config.yaml').write_text(yaml.safe_dump(config))
    monkeypatch.setattr(settings_module, 'PROJECT_ROOT', tmp_path)
    settings_module.get_settings.cache_clear()
    for key, value in {'agent_process': None, 'agent_processes': {}, 'agent_active_platforms': set(), 'agent_run_lock': None}.items():
        monkeypatch.setattr(state, key, value)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://testserver') as client:
            login = await client.post('/api/auth/login', json={'email': 'operator@example.invalid', 'password': 'test-password'})
            assert login.status_code == 200, login.text
            client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
            yield client
        await state.db_manager.engine.dispose()
    settings_module.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_all_read_only_feature_routes(dashboard):
    paths = [
        '/api/health', '/api/stats', '/api/jobs', '/api/jobs/inspector', '/api/applications',
        '/api/run-logs', '/api/config', '/api/config/linkedin', '/api/resume-profile',
        '/api/resume-optimization/analysis', '/api/scam-detector/analysis',
        '/api/analytics/company-distribution', '/api/analytics/location-distribution',
        '/api/analytics/keyword-performance', '/api/analytics/daily-timeline',
        '/api/analytics/success-rate-trend', '/api/application-statuses',
        '/api/market-intel/salary-benchmarks', '/api/market-intel/skill-demand',
        '/api/market-intel/competitor-companies', '/api/market-intel/win-rate-prediction',
        '/api/autopilot/config', '/api/autopilot/blacklist', '/api/autopilot/schedule',
        '/api/agent/status', '/api/agent/output', '/api/multi/status', '/api/multi/output?platform=naukri',
        '/api/cache/match-cache', '/api/cache/match-cache/stats', '/api/metrics', '/api/logs',
        '/api/session/status', '/api/sessions/list', '/api/backups', '/api/accounts', '/api/webhooks',
        '/api/applications/sync-status', '/api/export/full', '/api/export/jobs/csv',
        '/api/export/applications/csv', '/api/export/stats/json',
    ]
    for path in paths:
        response = await dashboard.get(path)
        assert response.status_code == 200, (path, response.text)
        assert response.headers['cache-control'] == 'private, no-store'


@pytest.mark.asyncio
async def test_private_routes_require_auth_even_without_operator_api_key(dashboard):
    dashboard.headers.pop('Authorization')
    for path in ('/api/config', '/api/accounts', '/api/export/full', '/api/jobs'):
        response = await dashboard.get(path)
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_accounts_create_edit_activate_delete(dashboard):
    created = await dashboard.post('/api/accounts', json={'email': 'second@example.invalid', 'password': 'secret', 'name': 'Second'})
    assert created.status_code == 200, created.text
    account_id = created.json()['account']['id']
    accounts = (await dashboard.get('/api/accounts')).json()['items']
    assert next(a for a in accounts if a['id'] == account_id)['email'] == 'second@example.invalid'
    response = await dashboard.put(f'/api/accounts/{account_id}', json={'name': 'Updated'})
    assert response.status_code == 200
    assert (await dashboard.post(f'/api/accounts/{account_id}/activate')).status_code == 200
    assert (await dashboard.delete(f'/api/accounts/{account_id}')).status_code == 200


@pytest.mark.asyncio
async def test_exports_roundtrip_remap_ids_and_dates_atomically(dashboard):
    now = datetime.now(UTC).isoformat()
    payload = {'data': {'jobs': [{'id': 800, 'naukri_job_id': 'test-job', 'title': 'Engineer', 'company': 'Example', 'url': 'https://www.naukri.com/job-listings-test-123', 'scraped_at': now}], 'applications': [{'id': 900, 'job_id': 800, 'status': 'failed', 'applied_at': now}], 'resume_profiles': []}}
    response = await dashboard.post('/api/import/full', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['counts']['applications'] == 1
    exported = (await dashboard.get('/api/export/full')).json()
    assert exported['data']['applications'][0]['job_id'] == exported['data']['jobs'][0]['id']
    repeated = await dashboard.post('/api/import/full', json=payload)
    assert repeated.json()['counts'] == {'jobs': 0, 'applications': 0, 'resume_profiles': 0}
    payload['data']['jobs'][0]['naukri_job_id'] = 'rollback-job'
    payload['data']['applications'][0]['job_id'] = 9999
    assert (await dashboard.post('/api/import/full', json=payload)).status_code == 422
    assert (await dashboard.get('/api/jobs')).json()['total'] == 1
    assert (await dashboard.get('/api/export/stats/json')).status_code == 200


@pytest.mark.asyncio
async def test_backup_restores_committed_database_and_rejects_traversal(dashboard):
    await dashboard.post('/api/accounts', json={'email': 'backup@example.invalid', 'password': 'test'})
    response = await dashboard.post('/api/backups/create')
    assert response.status_code == 200, response.text
    name = response.json()['name']
    account = next(a for a in (await dashboard.get('/api/accounts')).json()['items'] if a['email'] == 'backup@example.invalid')
    await dashboard.delete(f"/api/accounts/{account['id']}")
    response = await dashboard.post('/api/backups/restore', params={'name': name})
    assert response.status_code == 200, response.text
    assert any(a['email'] == 'backup@example.invalid' for a in (await dashboard.get('/api/accounts')).json()['items'])
    assert (await dashboard.post('/api/backups/restore', params={'name': '../'+name})).status_code == 404


@pytest.mark.asyncio
async def test_webhooks_and_autopilot_lists(dashboard):
    response = await dashboard.post('/api/webhooks', json={'name': 'Test', 'url': 'https://example.com/hook', 'events': 'application.applied'})
    assert response.status_code == 200, response.text
    webhook_id = response.json()['webhook']['id']
    assert (await dashboard.put(f'/api/webhooks/{webhook_id}', json={'name': 'Changed'})).status_code == 200
    assert (await dashboard.delete(f'/api/webhooks/{webhook_id}')).status_code == 200
    for name in ('blacklist', 'whitelist'):
        assert (await dashboard.post('/api/autopilot/'+name, json={'company': 'Test Company'})).status_code == 200
        response = await dashboard.request('DELETE', '/api/autopilot/'+name, json={'company': 'Test Company'})
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_clear_data_refuses_active_agent(dashboard, monkeypatch):
    monkeypatch.setattr(state, 'agent_process', Mock(poll=lambda: None))
    assert (await dashboard.delete('/api/data/clear-all')).status_code == 409
    monkeypatch.setattr(state, 'agent_process', None)
    response = await dashboard.delete('/api/data/clear-all')
    assert response.status_code == 200, response.text
    assert (await dashboard.get('/api/jobs')).json()['total'] == 0


@pytest.mark.asyncio
async def test_queue_never_marks_unsubmitted_jobs_applied(dashboard):
    async with state.db_manager.session_factory() as session:
        job = Job(naukri_job_id='queue-test', title='Engineer', company='Example', url='https://www.naukri.com/job-listings-queue-test')
        session.add(job)
        await session.commit()
        job_id = job.id
    response = await dashboard.post('/api/jobs/apply-batch', json={'job_ids': [job_id, job_id]})
    assert response.status_code == 200, response.text
    assert response.json()['queued_count'] == 1
    assert response.json()['applied_count'] == 0
    response = await dashboard.post('/api/jobs/apply-batch', json={'job_ids': [job_id]})
    assert response.json()['queued_count'] == 0
    apps = (await dashboard.get('/api/applications')).json()['items']
    assert apps[0]['status'] == 'pending_retry'
    assert (await dashboard.post(f"/api/applications/{apps[0]['id']}/retry")).status_code == 409


@pytest.mark.asyncio
async def test_scheduler_dispatches_queue_and_runs_schedule_once(dashboard, monkeypatch):
    from unittest.mock import AsyncMock
    from api.scheduler import tick
    from api.routes import agent
    launch = AsyncMock(return_value={'status': 'started'})
    monkeypatch.setattr(agent, 'start_agent', launch)
    monkeypatch.setattr(state, 'agent_queued_ids', [], raising=False)
    schedule = {'enabled': True, 'schedule': {'type': 'weekdays', 'time': '09:00', 'days': [], 'timezone': 'Asia/Kolkata'}}
    assert (await dashboard.put('/api/autopilot/config', json=schedule)).status_code == 200
    now = datetime(2026, 10, 12, 4, 0, tzinfo=UTC)
    await tick(now)
    await tick(now)
    assert launch.await_count == 1
    launch.reset_mock()
    async with state.db_manager.session_factory() as session:
        job = Job(naukri_job_id='dispatch', title='Engineer', company='Example', url='https://www.naukri.com/job-listings-dispatch')
        session.add(job)
        await session.flush()
        session.add(Application(job_id=job.id, status='pending_retry'))
        await session.commit()
        job_id = job.id
    await tick(now)
    launch.assert_awaited_once_with(platform='naukri', job_ids=[job_id])
    assert (await dashboard.put('/api/autopilot/config', json={'schedule': {'type': 'daily', 'time': '99:99', 'days': []}})).status_code == 422


@pytest.mark.asyncio
async def test_sync_persists_only_observed_results(dashboard, monkeypatch):
    from unittest.mock import AsyncMock
    from api import application_sync
    async with state.db_manager.session_factory() as session:
        job = Job(naukri_job_id='sync', title='Engineer', company='Example', url='https://www.naukri.com/job-listings-sync')
        session.add(job)
        await session.flush()
        session.add(Application(job_id=job.id, status='applied'))
        await session.commit()
        job_id = job.id
    observer = AsyncMock(return_value={})
    monkeypatch.setattr(application_sync, 'observe_applications', observer)
    await application_sync.sync_applications()
    assert (await dashboard.get('/api/applications/sync-status')).json()['items'] == []
    observer.return_value = {job_id: 'applied'}
    await application_sync.sync_applications()
    result = (await dashboard.get('/api/applications/sync-status')).json()
    assert result['items'][0]['naukri_status'] == 'applied'
    assert result['synced_count'] == 1


@pytest.mark.asyncio
async def test_resume_upload_without_ai_and_profile_edit(dashboard):
    import fitz
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), 'Alex Example\nAlex@example.invalid\nPython Software Engineer\nSkills: Python, SQL, Java\nExperience: 3 years')
    content = document.tobytes()
    document.close()
    response = await dashboard.post('/api/resume/upload', files={'file': ('resume.pdf', content, 'application/pdf')})
    assert response.status_code == 200, response.text
    profile = response.json()['profile']
    profile['summary'] = 'Edited profile'
    assert (await dashboard.put('/api/resume/profile', json=profile)).status_code == 200
    assert (await dashboard.get('/api/resume-profile')).json()['profile']['summary'] == 'Edited profile'
    config = yaml.safe_load((state.settings.project_root / 'config.yaml').read_text())
    assert config['resume']['path']


@pytest.mark.asyncio
async def test_webhook_test_targets_selected_destination(dashboard, monkeypatch):
    import httpx
    from api.routes import webhooks
    from unittest.mock import AsyncMock
    posted = []
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            posted.append(url)
            return httpx.Response(200)
    ids = []
    for number in (1, 2):
        response = await dashboard.post('/api/webhooks', json={'name': f'Webhook {number}', 'url': f'https://example.com/{number}'})
        ids.append(response.json()['webhook']['id'])
    monkeypatch.setattr(webhooks.httpx, 'AsyncClient', FakeClient)
    result = await dashboard.post(f'/api/webhooks/{ids[0]}/test')
    assert result.status_code == 200, result.text
    assert posted == ['https://example.com/1']


@pytest.mark.asyncio
async def test_company_preferences_and_daily_limits(dashboard):
    from api.company_policy import CompanyPolicy
    response = await dashboard.put('/api/autopilot/config', json={
        'enabled': True, 'schedule': {'time': '23:59'},
        'company_blacklist': ['Blocked'], 'company_whitelist': ['Preferred'],
        'tier_map': {'Preferred': 'top_tier'}, 'throttle': {'top_tier_daily': 1},
    })
    assert response.status_code == 200
    policy = CompanyPolicy(state.settings, 'naukri')
    assert policy.priority('preferred') == 1
    assert (await policy.allowed('BLOCKED', state.repo, 'naukri'))[0] is False
    assert (await policy.allowed('Preferred', state.repo, 'naukri'))[0] is True
    job = await state.repo.save_job(naukri_job_id='policy-job', title='Engineer', company='Preferred', url='https://www.naukri.com/test')
    await state.repo.save_application(job_id=job.id, match_score=90, status='applied')
    assert (await policy.allowed('Preferred', state.repo, 'naukri'))[0] is False


@pytest.mark.asyncio
async def test_runtime_webhook_publisher_uses_committed_outcomes(dashboard, monkeypatch):
    from datetime import timedelta
    from unittest.mock import AsyncMock
    from api.webhook_publisher import publish_since
    from api.routes import webhooks
    deliver = AsyncMock(return_value=[])
    monkeypatch.setattr(webhooks, 'fire_webhook_event', deliver)
    start = datetime.now(UTC)
    job = await state.repo.save_job(naukri_job_id='event-job', title='Engineer', company='Example', url='https://www.naukri.com/test')
    await state.repo.save_application(job_id=job.id, match_score=90, status='applied')
    end = datetime.now(UTC) + timedelta(seconds=1)
    await publish_since(start, end)
    deliver.assert_awaited_once()
    assert deliver.await_args.args[0] == 'application.created'
    assert deliver.await_args.args[1]['job_id'] == job.id
    deliver.reset_mock()
    await publish_since(end, end + timedelta(seconds=1))
    deliver.assert_not_awaited()


def test_priority_conditions_use_scores_and_reject_code():
    from api.priority_rules import parse_condition, priority
    config = {'priority_rules': [{'enabled': True, 'action': 'apply_immediately', 'condition': 'match_score > 90 AND posted_hours < 24'}]}
    assert priority(config, 95, '2 hours ago') == 1
    assert priority(config, 80, '2 hours ago') == 0
    assert priority(config, 95, '3 days ago') == 0
    with pytest.raises(ValueError):
        parse_condition('__import__("os").system("true")')


@pytest.mark.asyncio
async def test_stats_filter_counts_and_recent_apps_by_platform(dashboard):
    async with state.db_manager.session_factory() as session, session.begin():
        for source, status in [('naukri', 'applied'), ('linkedin', 'failed'), ('linkedin', 'pending_retry')]:
            job = Job(naukri_job_id=source+status, title='Engineer', company=source, url='https://example.invalid/job', source=source)
            session.add(job)
            await session.flush()
            session.add(Application(job_id=job.id, source=source, status=status))
    naukri = (await dashboard.get('/api/stats?source=naukri')).json()
    linkedin = (await dashboard.get('/api/stats?source=linkedin')).json()
    assert naukri['stats']['applied'] == naukri['today_applied'] == 1
    assert naukri['stats']['failed'] == 0
    assert linkedin['stats']['failed'] == 1
    assert linkedin['today_applied'] == 0
    assert {a['company'] for a in linkedin['recent_applications']} == {'linkedin'}


@pytest.mark.asyncio
async def test_queued_claim_reuses_record_and_blocks_duplicate(dashboard):
    from api.job_queue import enqueue_jobs
    job = await state.repo.save_job(naukri_job_id='claim-queue', title='Engineer', company='Example', url='https://www.naukri.com/test')
    factory = await state.db_manager.get_session_factory()
    assert await enqueue_jobs(factory, [job.id]) == 1
    await state.repo.initialize()
    assert not state.repo.is_already_applied(job.naukri_job_id)
    app_id = await state.repo.begin_application(job.id, 87, 'Resume fit', 'Java', 'Go')
    assert state.repo.is_already_applied(job.naukri_job_id)
    assert await enqueue_jobs(factory, [job.id]) == 0
    await state.repo.finalize_application(app_id, 'applied')
    async with factory() as session:
        rows = (await session.execute(select(Application).where(Application.job_id == job.id))).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == 'applied'
        assert rows[0].match_score == 87


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['failed', 'skipped_dry_run'])
async def test_queued_save_reuses_record_and_updates_metadata(dashboard, outcome):
    from api.job_queue import enqueue_jobs
    job = await state.repo.save_job(naukri_job_id='save-queue', title='Engineer', company='Example', url='https://www.naukri.com/test')
    factory = await state.db_manager.get_session_factory()
    await enqueue_jobs(factory, [job.id])
    result = await state.repo.save_application(job.id, 72, outcome, 'Reason', 'Python', 'Java', 'Diagnostic')
    async with factory() as session:
        rows = (await session.execute(select(Application).where(Application.job_id == job.id))).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == result.id
        assert rows[0].status == outcome
        assert rows[0].match_reasoning == 'Reason'
        assert rows[0].error_message == 'Diagnostic'
