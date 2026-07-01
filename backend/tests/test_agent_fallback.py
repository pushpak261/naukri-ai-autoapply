from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.naukri_agent.ai.similarity import VectorSimilarityFilter
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.domain.entities import Job, JobApplication, ResumeProfile
from src.naukri_agent.core.exceptions import LLMQuotaExceededError
from src.naukri_agent.orchestrator.agent import NaukriAgent


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.application.daily_cap = 5
    settings.application.match_score_threshold = 40
    settings.application.dry_run = False
    settings.application.delay_between_applies_min = 1
    settings.application.delay_between_applies_max = 2
    settings.ai.model = "primary-model"
    settings.ai.fallback_model = "fallback-model"
    settings.ai.abort_on_quota = True
    return settings


@pytest.mark.asyncio
async def test_process_jobs_quota_fallback_success(mock_settings):
    # Setup mock factory and agent
    mock_factory = MagicMock()
    mock_factory.get_settings.return_value = mock_settings

    mock_provider = MagicMock()
    mock_factory.get_llm_provider.return_value = mock_provider

    mock_engine = MagicMock()
    mock_engine.page.goto = AsyncMock()
    mock_factory.get_browser_engine.return_value = mock_engine

    mock_interactions = MagicMock()
    mock_interactions.wait_for_navigation_complete = AsyncMock()
    mock_interactions.action_delay = AsyncMock()
    mock_factory.get_browser_interactions.return_value = mock_interactions

    agent = NaukriAgent(mock_factory)
    agent._resume_profile = ResumeProfile(
        name="Test Developer",
        skills=["Python"],
        total_experience_years=3.0,
        current_title="Developer",
        summary="Dev",
    )
    agent._repo = MagicMock()
    agent._repo.get_today_application_count = AsyncMock(return_value=0)
    agent._repo.is_already_applied = MagicMock(return_value=False)
    agent._repo.save_job = AsyncMock(side_effect=lambda **kwargs: Job(id=1, **kwargs))
    agent._repo.save_application = AsyncMock()

    # Mock parameters
    jobs = [
        Job(
            naukri_job_id="job_123",
            title="Python Developer",
            company="Tech Corp",
            url="http://example.com/job",
            description="Python developer needed",
            skills="Python",
        )
    ]

    mock_matcher = AsyncMock()
    # First match call raises quota limit, second match call succeeds
    mock_matcher.match.side_effect = [
        LLMQuotaExceededError("Quota exhausted", is_daily_quota=True),
        JobApplication(
            match_score=80.0,
            should_apply=True,
            match_reasoning="Fits perfectly",
            matching_skills="Python",
        ),
    ]

    mock_applier = AsyncMock()
    mock_applier.apply_to_job.return_value = {"status": "applied"}

    mock_searcher = AsyncMock()

    vector_filter = MagicMock(spec=VectorSimilarityFilter)
    vector_filter.get_similarity_score.return_value = 0.5

    # Call _process_jobs
    with (
        patch("src.naukri_agent.orchestrator.agent.log_warning"),
        patch("src.naukri_agent.orchestrator.agent.log_success"),
        patch("asyncio.sleep", return_value=None),
    ):
        await agent._process_jobs(jobs, mock_matcher, mock_applier, mock_searcher, vector_filter)

    # Verify fallback switched
    assert mock_settings.ai.model == "fallback-model"
    assert mock_settings.ai.fallback_model is None
    mock_provider.set_model.assert_called_once_with("fallback-model")
    assert mock_matcher.match.call_count == 2
    assert agent._jobs_applied == 1


@pytest.mark.asyncio
async def test_process_jobs_quota_no_fallback_abort(mock_settings):
    # No fallback model
    mock_settings.ai.fallback_model = None
    mock_settings.ai.abort_on_quota = True

    mock_factory = MagicMock()
    mock_factory.get_settings.return_value = mock_settings

    mock_engine = MagicMock()
    mock_engine.page.goto = AsyncMock()
    mock_factory.get_browser_engine.return_value = mock_engine

    mock_interactions = MagicMock()
    mock_interactions.wait_for_navigation_complete = AsyncMock()
    mock_interactions.action_delay = AsyncMock()
    mock_factory.get_browser_interactions.return_value = mock_interactions

    agent = NaukriAgent(mock_factory)
    agent._resume_profile = ResumeProfile(
        name="Test Developer",
        skills=["Python"],
        total_experience_years=3.0,
        current_title="Developer",
        summary="Dev",
    )
    agent._repo = MagicMock()
    agent._repo.get_today_application_count = AsyncMock(return_value=0)
    agent._repo.is_already_applied = MagicMock(return_value=False)
    agent._repo.save_job = AsyncMock(side_effect=lambda **kwargs: Job(id=1, **kwargs))
    agent._repo.save_application = AsyncMock()

    jobs = [
        Job(
            naukri_job_id="job_1",
            title="Python Developer",
            company="Tech Corp",
            url="http://example.com/job1",
            description="Python developer needed",
            skills="Python",
        ),
        Job(
            naukri_job_id="job_2",
            title="Django Developer",
            company="Web Corp",
            url="http://example.com/job2",
            description="Django developer needed",
            skills="Python",
        ),
    ]

    mock_matcher = AsyncMock()
    mock_matcher.match.side_effect = LLMQuotaExceededError("Quota exhausted", is_daily_quota=True)

    mock_applier = AsyncMock()
    mock_searcher = AsyncMock()

    vector_filter = MagicMock(spec=VectorSimilarityFilter)
    vector_filter.get_similarity_score.return_value = 0.5

    with (
        patch("src.naukri_agent.orchestrator.agent.log_error"),
        patch("asyncio.sleep", return_value=None),
    ):
        await agent._process_jobs(jobs, mock_matcher, mock_applier, mock_searcher, vector_filter)

    # Should abort on first job and not process the second
    assert mock_matcher.match.call_count == 1
    assert agent._jobs_applied == 0
    assert agent._interrupted is True


@pytest.mark.asyncio
async def test_process_jobs_quota_no_fallback_continue(mock_settings):
    # No fallback model but abort_on_quota is False
    mock_settings.ai.fallback_model = None
    mock_settings.ai.abort_on_quota = False

    mock_factory = MagicMock()
    mock_factory.get_settings.return_value = mock_settings

    mock_engine = MagicMock()
    mock_engine.page.goto = AsyncMock()
    mock_factory.get_browser_engine.return_value = mock_engine

    mock_interactions = MagicMock()
    mock_interactions.wait_for_navigation_complete = AsyncMock()
    mock_interactions.action_delay = AsyncMock()
    mock_factory.get_browser_interactions.return_value = mock_interactions

    agent = NaukriAgent(mock_factory)
    agent._resume_profile = ResumeProfile(
        name="Test Developer",
        skills=["Python"],
        total_experience_years=3.0,
        current_title="Developer",
        summary="Dev",
    )
    agent._repo = MagicMock()
    agent._repo.get_today_application_count = AsyncMock(return_value=0)
    agent._repo.is_already_applied = MagicMock(return_value=False)
    agent._repo.save_job = AsyncMock(side_effect=lambda **kwargs: Job(id=1, **kwargs))
    agent._repo.save_application = AsyncMock()

    jobs = [
        Job(
            naukri_job_id="job_1",
            title="Python Developer",
            company="Tech Corp",
            url="http://example.com/job1",
            description="Python developer needed",
            skills="Python",
        ),
        Job(
            naukri_job_id="job_2",
            title="Django Developer",
            company="Web Corp",
            url="http://example.com/job2",
            description="Django developer needed",
            skills="Python",
        ),
    ]

    mock_matcher = AsyncMock()
    mock_matcher.match.side_effect = [
        LLMQuotaExceededError("Quota exhausted", is_daily_quota=True),
        JobApplication(
            match_score=80.0,
            should_apply=True,
            match_reasoning="Fits perfectly",
            matching_skills="Python",
        ),
    ]

    mock_applier = AsyncMock()
    mock_applier.apply_to_job.return_value = {"status": "applied"}
    mock_searcher = AsyncMock()

    vector_filter = MagicMock(spec=VectorSimilarityFilter)
    vector_filter.get_similarity_score.return_value = 0.5

    with (
        patch("src.naukri_agent.orchestrator.agent.log_error"),
        patch("src.naukri_agent.orchestrator.agent.log_warning"),
        patch("asyncio.sleep", return_value=None),
    ):
        await agent._process_jobs(jobs, mock_matcher, mock_applier, mock_searcher, vector_filter)

    # Should continue to second job and apply successfully
    assert mock_matcher.match.call_count == 2
    assert agent._jobs_applied == 1
    assert agent._jobs_failed == 1
    assert agent._interrupted is False


@pytest.mark.asyncio
async def test_agent_constructor_di(mock_settings):
    mock_repo = MagicMock()
    mock_engine = MagicMock()
    mock_interactions = MagicMock()
    mock_llm = MagicMock()
    mock_parser = MagicMock()
    mock_login = MagicMock()
    mock_searcher = MagicMock()
    mock_matcher = MagicMock()
    mock_refresher = MagicMock()

    agent = NaukriAgent(
        settings=mock_settings,
        repository=mock_repo,
        browser_engine=mock_engine,
        browser_interactions=mock_interactions,
        llm_provider=mock_llm,
        resume_parser=mock_parser,
        login_handler=mock_login,
        job_searcher=mock_searcher,
        job_matcher=mock_matcher,
        question_answerer_factory=lambda p: MagicMock(),
        job_applier_factory=lambda qa: MagicMock(),
        profile_refresher=mock_refresher,
    )

    assert agent._settings == mock_settings
    assert agent._repo == mock_repo
    assert agent._engine == mock_engine
    assert agent._interactions == mock_interactions
    assert agent._llm == mock_llm
    assert agent._resume_parser == mock_parser
    assert agent._login_handler == mock_login
    assert agent._job_searcher == mock_searcher
    assert agent._job_matcher == mock_matcher
    assert agent._profile_refresher == mock_refresher
