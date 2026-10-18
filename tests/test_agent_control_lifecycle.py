"""Command Center lifecycle regressions; no real subprocesses or job sites."""
import asyncio
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.deps import AppState, current_state
from api.routes import agent, multi_agent


@pytest.fixture
def runtime():
    value = AppState()
    value.repo = SimpleNamespace(get_run_stats=AsyncMock(return_value=[]))
    token = current_state.set(value)
    yield value
    current_state.reset(token)


def process(pid=101):
    return MagicMock(pid=pid, poll=MagicMock(return_value=None), stdout=None, stderr=None)


@pytest.mark.asyncio
async def test_parallel_view_can_see_stop_and_read_single_run(runtime, monkeypatch):
    proc = process()
    runtime.agent_process = proc
    runtime.agent_platform = 'linkedin'
    runtime.agent_started_at = datetime.now(UTC)
    runtime.agent_output_buffer = ['last output\n']
    status = await multi_agent.agents_status()
    assert status['agents']['linkedin']['running']
    assert status['agents']['linkedin']['pid'] == proc.pid
    assert (await multi_agent.agents_output('linkedin', 10)).body == b'last output\n'
    def terminate(value):
        value.poll.return_value = 0
    monkeypatch.setattr(agent, 'stop_agent_process', terminate)
    assert (await multi_agent.stop_agents(None))['agents']['linkedin']['status'] == 'stopped'
    assert runtime.agent_process is None
    assert runtime.agent_output_buffer == ['last output\n']


@pytest.mark.asyncio
async def test_failed_termination_retains_process_for_retry(runtime, monkeypatch):
    proc = process()
    runtime.agent_process = proc
    monkeypatch.setattr(agent, 'stop_agent_process', lambda value: None)
    with pytest.raises(HTTPException) as error:
        await agent.stop_agent()
    assert error.value.status_code == 503
    assert runtime.agent_process is proc


@pytest.mark.asyncio
async def test_stop_waits_for_inflight_start(runtime):
    from api.agent_runtime import serialized_start, serialized_stop
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []
    @serialized_start
    async def start():
        started.set()
        await release.wait()
        calls.append('started')
    @serialized_stop
    async def stop():
        calls.append('stopped')
    pending_start = asyncio.create_task(start())
    await started.wait()
    pending_stop = asyncio.create_task(stop())
    await asyncio.sleep(0)
    assert calls == []
    release.set()
    await asyncio.gather(pending_start, pending_stop)
    assert calls == ['started', 'stopped']


@pytest.mark.asyncio
@pytest.mark.parametrize('parallel', [False, True])
async def test_reader_delivers_on_event_loop_and_ignores_obsolete_process(runtime, parallel):
    queue = asyncio.Queue()
    proc = process()
    proc.stdout = BytesIO(b'hello\n')
    if parallel:
        multi_agent._ensure_platform('naukri')
        runtime.agent_processes['naukri'] = proc
        runtime.agent_sse_clients_map['naukri'].append(queue)
        multi_agent._start_output_reader('naukri', proc)
    else:
        runtime.agent_process = proc
        runtime.agent_sse_clients.append(queue)
        agent._start_output_reader(proc)
    assert await asyncio.wait_for(queue.get(), 2) == 'hello\n'
    obsolete = process(202)
    obsolete.stdout = BytesIO(b'obsolete\n')
    if parallel:
        multi_agent._start_output_reader('naukri', obsolete)
    else:
        agent._start_output_reader(obsolete)
    await asyncio.sleep(0.05)
    assert queue.empty()


@pytest.mark.asyncio
async def test_zero_history_has_no_replay_and_stream_unregisters(runtime):
    multi_agent._ensure_platform('naukri')
    runtime.agent_output_buffers['naukri'] = ['old\n']
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    response = await multi_agent.agents_output_stream(request, 'naukri', 0)
    queue = runtime.agent_sse_clients_map['naukri'][0]
    assert queue.empty()
    queue.put_nowait('new\nsecond\n')
    iterator = response.body_iterator
    assert await anext(iterator) == 'data: new\ndata: second\n\n'
    await iterator.aclose()
    assert runtime.agent_sse_clients_map['naukri'] == []


@pytest.mark.asyncio
async def test_unknown_stop_platform_does_not_create_state(runtime):
    with pytest.raises(HTTPException):
        await multi_agent.stop_agents('unknown')
    assert runtime.agent_processes == {}


@pytest.mark.asyncio
async def test_parallel_spawn_failure_preserves_successful_platform(runtime, tmp_path, monkeypatch):
    from api import agent_runtime, tenants
    runtime.settings = SimpleNamespace(project_root=tmp_path)
    runtime.active_account_email = 'test@example.invalid'
    monkeypatch.setattr(tenants, 'validate_agent_configuration', AsyncMock())
    monkeypatch.setattr(tenants, 'agent_environment', lambda: {})
    monkeypatch.setattr(agent_runtime, 'ensure_browser_capacity', lambda: None)
    proc = process()
    monkeypatch.setattr(multi_agent, 'spawn_agent', MagicMock(side_effect=[proc, OSError('launch failed')]))
    result = await multi_agent.start_agents(['naukri', 'linkedin'])
    assert result['agents']['naukri']['status'] == 'started'
    assert result['agents']['linkedin']['status'] == 'error'
    assert runtime.agent_processes['naukri'] is proc
    assert runtime.agent_processes['linkedin'] is None


@pytest.mark.asyncio
async def test_status_still_reports_process_when_optional_run_history_fails(runtime):
    runtime.agent_process = process()
    runtime.repo.get_run_stats.side_effect = RuntimeError('History unavailable')
    result = await agent.agent_status()
    assert result['running']
    assert result['last_run'] is None


@pytest.mark.asyncio
async def test_log_query_limits_are_validated(runtime):
    import httpx
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(agent.router)
    app.include_router(multi_agent.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for path in ('/api/agent/output?lines=0', '/api/agent/output?lines=-1',
                     '/api/multi/output?platform=naukri&lines=60001',
                     '/api/agent/output/stream?history=-1',
                     '/api/multi/output/stream?platform=naukri&history=60001'):
            assert (await client.get(path)).status_code == 422
