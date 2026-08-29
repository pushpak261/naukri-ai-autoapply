from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.naukri_agent.utils.similarity import VectorSimilarityFilter
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.models.entities import Job, ResumeProfile
from src.naukri_agent.bot.agent import NaukriAgent


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
    settings.search.enable_heuristics = False
    settings.search.experience_max = 2
    return settings


def _make_agent(mock_settings):
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
        skills=["Java"],
        total_experience_years=1.0,
        current_title="Developer",
        summary="Dev",
    )
    agent._repo = MagicMock()
    agent._repo.get_today_application_count = AsyncMock(return_value=0)
    agent._repo.is_already_applied = MagicMock(return_value=False)
    agent._repo.save_job = AsyncMock(side_effect=lambda **kwargs: Job(id=1, **kwargs))
    agent._repo.begin_application = AsyncMock(return_value=1)
    agent._repo.finalize_application = AsyncMock()
    agent._repo.save_application = AsyncMock()
    return agent, mock_engine, mock_interactions


@pytest.mark.asyncio
async def test_process_jobs_targeted_java_applied_directly(mock_settings):
    # The targeting gate applies Java/Spring roles directly (no AI match call)
    # so the matcher is intentionally bypassed to save tokens.
    agent, _, _ = _make_agent(mock_settings)

    jobs = [
        Job(
            naukri_job_id="job_1",
            title="Java Developer",
            company="Tech Corp",
            url="http://example.com/job1",
            description="Java Spring Boot backend developer",
            skills="Java, Spring",
        )
    ]

    mock_matcher = AsyncMock()
    mock_applier = AsyncMock()
    mock_applier.apply_to_job.return_value = {"status": "applied"}
    mock_searcher = AsyncMock()
    vector_filter = MagicMock(spec=VectorSimilarityFilter)
    vector_filter.get_similarity_score.return_value = 0.5

    with (
        patch("src.naukri_agent.bot.agent.log_info"),
        patch("asyncio.sleep", return_value=None),
    ):
        await agent._process_jobs(jobs, mock_matcher, mock_applier, mock_searcher, vector_filter)

    mock_matcher.match.assert_not_called()
    assert agent._jobs_applied == 1
    assert agent._jobs_skipped == 0


@pytest.mark.asyncio
async def test_process_jobs_non_target_skipped(mock_settings):
    # Non-target stacks (e.g. Python) are skipped at the targeting gate
    # before any AI matcher call.
    agent, _, _ = _make_agent(mock_settings)

    jobs = [
        Job(
            naukri_job_id="job_1",
            title="Python Developer",
            company="Tech Corp",
            url="http://example.com/job1",
            description="Python developer needed",
            skills="Python",
        )
    ]

    mock_matcher = AsyncMock()
    mock_applier = AsyncMock()
    mock_searcher = AsyncMock()
    vector_filter = MagicMock(spec=VectorSimilarityFilter)
    vector_filter.get_similarity_score.return_value = 0.5

    with (
        patch("src.naukri_agent.bot.agent.log_info"),
        patch("asyncio.sleep", return_value=None),
    ):
        await agent._process_jobs(jobs, mock_matcher, mock_applier, mock_searcher, vector_filter)

    mock_matcher.match.assert_not_called()
    assert agent._jobs_applied == 0
    assert agent._jobs_skipped == 1


@pytest.mark.asyncio
async def test_process_jobs_senior_role_skipped(mock_settings):
    # Senior Java roles (experience above the 0-2 yr target) are skipped.
    agent, _, _ = _make_agent(mock_settings)

    jobs = [
        Job(
            naukri_job_id="job_1",
            title="Senior Java Developer",
            company="Tech Corp",
            url="http://example.com/job1",
            description="Java Spring Boot backend developer",
            skills="Java, Spring",
            experience="5-8 Yrs",
        )
    ]

    mock_matcher = AsyncMock()
    mock_applier = AsyncMock()
    mock_searcher = AsyncMock()
    vector_filter = MagicMock(spec=VectorSimilarityFilter)
    vector_filter.get_similarity_score.return_value = 0.5

    with (
        patch("src.naukri_agent.bot.agent.log_info"),
        patch("asyncio.sleep", return_value=None),
    ):
        await agent._process_jobs(jobs, mock_matcher, mock_applier, mock_searcher, vector_filter)

    mock_matcher.match.assert_not_called()
    assert agent._jobs_applied == 0
    assert agent._jobs_skipped == 1


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
