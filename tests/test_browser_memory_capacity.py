"""Prevent browser starts from taking down a memory-constrained dashboard."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api import agent_runtime as runtime


@pytest.mark.parametrize('content,expected', [('536870912', 512), ('1073741824', 1024), ('max', None), ('9223372036854771712', None), ('invalid', None)])
def test_cgroup_memory_limits(monkeypatch, content, expected):
    from pathlib import Path
    def read(path, *args, **kwargs):
        if str(path).endswith('memory.max'):
            return content
        raise FileNotFoundError()
    monkeypatch.setattr(Path, 'read_text', read)
    assert runtime.container_memory_limit_mb() == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('limit,active,blocked', [(512, 0, True), (1024, 0, False), (1024, 1, True), (2048, 1, False), (None, 0, False)])
async def test_memory_budget_protects_api_and_existing_agents(monkeypatch, limit, active, blocked):
    from api import deps, tenants, remote_verification
    process = MagicMock(poll=MagicMock(return_value=None))
    state = SimpleNamespace(agent_process=process if active else None, agent_processes={}, application_sync_task=None)
    monkeypatch.setattr(deps, 'root_state', state)
    monkeypatch.setattr(tenants, 'runtimes', {})
    monkeypatch.setattr(remote_verification.controller, 'active', lambda: False)
    monkeypatch.setattr(runtime, 'container_memory_limit_mb', lambda: limit)
    if blocked:
        with pytest.raises(HTTPException) as error:
            runtime.ensure_browser_capacity(maximum=2)
        assert error.value.status_code == 503
        assert 'memory' in error.value.detail.lower()
    else:
        runtime.ensure_browser_capacity(maximum=2)
