"""Regressions found during the client readiness logic audit."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.scheduler import due_key


def test_scheduler_canonicalizes_single_digit_time():
    config = {"enabled": True, "schedule": {
        "type": "daily", "time": "9:5", "timezone": "UTC", "days": [],
    }}
    assert due_key(config, datetime(2026, 10, 17, 10, 0, tzinfo=UTC)) == "2026-10-17:09:05:UTC"
    assert due_key(config, datetime(2026, 10, 17, 9, 4, tzinfo=UTC)) is None


@pytest.mark.asyncio
async def test_linkedin_run_reaches_processing_with_title_exclusions(tmp_path, monkeypatch):
    from src.linked_agent.bot import agent as module
    from src.linked_agent.config.settings import Settings
    from src.linked_agent.models.entities import Job

    settings = Settings(project_root=tmp_path)
    settings.exclusions.enable_scam_filter = False
    settings.exclusions.title_keywords = ["Sales"]
    repository = AsyncMock()
    repository.get_all_job_descriptions.return_value = []
    searcher = AsyncMock()
    searcher.search_all.return_value = [Job(
        linkedin_job_id="audit", title="Software Engineer", company="Example",
        url="https://example.com/jobs/audit", description="Python developer",
    )]
    agent = module.LinkedInAgent(
        settings=settings, repository=repository, browser_engine=AsyncMock(),
        browser_interactions=MagicMock(), llm_provider=MagicMock(),
        resume_parser=MagicMock(), login_handler=AsyncMock(), job_searcher=searcher,
        job_matcher=MagicMock(), question_answerer_factory=MagicMock(),
        job_applier_factory=MagicMock(),
    )
    agent._resume_profile = SimpleNamespace(skills=["Python"], current_title="Engineer", summary="Developer")
    agent._parse_resume = AsyncMock()
    agent._process_jobs = AsyncMock()
    agent._cleanup = AsyncMock()
    monkeypatch.setattr(agent, "_print_banner", lambda: None)
    monkeypatch.setattr(agent, "_register_signal_handlers", lambda: None)
    monkeypatch.setattr(module, "setup_logging", lambda **kwargs: None)
    await agent.run(dry_run=True)
    assert not agent._run_error
    agent._process_jobs.assert_awaited_once()
    assert not agent._exclusion_spec.is_satisfied_by(searcher.search_all.return_value[0])


@pytest.mark.asyncio
async def test_skill_breakdown_has_disjoint_ranges(tmp_path, monkeypatch):
    from api.routes import resume_optimization as module

    rows = []
    for _ in range(4):
        rows.append((SimpleNamespace(matching_skills='["Python", "SQL"]', missing_skills='["Rust"]'), None))
    rows.append((SimpleNamespace(matching_skills='["Python"]', missing_skills='["SQL", "Rust"]'), None))
    session = AsyncMock()
    applications = MagicMock()
    applications.all.return_value = rows
    jobs = MagicMock()
    jobs.scalars.return_value.all.return_value = []
    session.execute.side_effect = [applications, jobs]
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    manager = SimpleNamespace(get_session_factory=AsyncMock(return_value=lambda: context))
    monkeypatch.setattr(module, "state", SimpleNamespace(settings=SimpleNamespace(project_root=tmp_path), db_manager=manager))
    result = await module.get_resume_optimization()
    assert {item['name']: item['count'] for item in result['skill_breakdown']} == {'Strong': 2, 'Moderate': 0, 'Weak': 1}
    assert sum(item['count'] for item in result['skill_breakdown']) == len(result['skills_data'])
    assert module._parse_skills('["Python", 42, null]') == ['Python']
