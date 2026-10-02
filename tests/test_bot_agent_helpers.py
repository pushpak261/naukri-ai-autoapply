"""Shared fakes and builders for the NaukriAgent test suites.

Everything here is deterministic and offline: no real browser, no real SMTP,
no real sleeps. The builders return MagicMock/AsyncMock collaborators whose
signatures mirror the protocols in ``src.naukri_agent.bot.interfaces``.
"""

from __future__ import annotations

import contextlib
import itertools
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.naukri_agent.bot.agent import NaukriAgent
from src.naukri_agent.config.settings import ExclusionSettings
from src.naukri_agent.models.entities import Job, JobApplication, ResumeProfile

__all__ = [
    "StubPipeline",
    "StubVectorFilter",
    "apply_job_details",
    "java_job",
    "make_agent",
    "make_applier",
    "make_engine",
    "make_interactions",
    "make_job",
    "make_matcher",
    "make_parser",
    "make_parser_without_profile",
    "make_profile",
    "make_repo",
    "make_searcher",
    "make_settings",
    "quiet_async",
]

_JOB_IDS = itertools.count(1000)
_UNSET = object()


# ---------------------------------------------------------------------------
# Behaviour stubs (real logic where cheap, scripted responses where not)
# ---------------------------------------------------------------------------


class StubVectorFilter:
    """Deterministic stand-in for :class:`VectorSimilarityFilter`."""

    def __init__(self, score: float = 0.0) -> None:
        self.score = score
        self.calls: list[str] = []

    def get_similarity_score(self, job_text: str) -> float:
        self.calls.append(job_text)
        return self.score


class StubPipeline:
    """Scriptable stand-in for :class:`FakeJobDetectionPipeline`.

    ``excluded`` may be a bool or a sequence consumed one entry per
    ``is_excluded`` call (the last entry repeats). ``deep_scam`` works the
    same way for ``deep_scam_check``.
    """

    def __init__(
        self,
        excluded: bool | list[bool] | None = False,
        deep_scam: bool | list[bool] | None = False,
        is_scam_filter_enabled: bool = True,
    ) -> None:
        self._excluded = excluded
        self._deep_scam = deep_scam
        self.is_scam_filter_enabled = is_scam_filter_enabled
        self.is_excluded_calls: list[tuple[str, float | None]] = []
        self.deep_scam_calls: list[str] = []
        self.build_calls = 0

    @staticmethod
    def _next(value, index: int) -> bool:
        if isinstance(value, bool):
            return value
        if not value:
            return False
        return bool(value[min(index, len(value) - 1)])

    def build_exclusion_spec(self) -> None:
        self.build_calls += 1

    def is_excluded(self, job: Job, heuristic_score: float | None = None) -> bool:
        self.is_excluded_calls.append((job.naukri_job_id, heuristic_score))
        return self._next(self._excluded, len(self.is_excluded_calls) - 1)

    def deep_scam_check(self, job: Job) -> bool:
        self.deep_scam_calls.append(job.naukri_job_id)
        return self._next(self._deep_scam, len(self.deep_scam_calls) - 1)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def make_settings(tmp_path=None, **sections) -> MagicMock:
    """Build a settings double whose path-ish fields are real values."""
    if tmp_path is not None:
        tmp_path = Path(tmp_path)
    settings = MagicMock(name="settings")
    settings.application.daily_cap = 5
    settings.application.match_score_threshold = 40
    settings.application.dry_run = False
    settings.application.delay_between_applies_min = 0
    settings.application.delay_between_applies_max = 0
    settings.application.answer_questions_with_pdf = True
    settings.application.collect_external_jobs = False
    settings.application.email_notifications_enabled = False
    settings.application.notify_on_scam = True
    settings.application.notify_on_apply = True

    settings.search.keywords = ["Java Developer"]
    settings.search.locations = ["Bangalore"]
    settings.search.experience_min = 0
    settings.search.experience_max = 2
    settings.search.enable_heuristics = False

    settings.ai.enable_matching = True
    settings.ai.model = "gemini-2.5-flash"

    settings.logging.level = "INFO"
    settings.logging.log_to_file = False
    settings.logging.log_dir = "data/logs"

    settings.resume.path = ""
    settings.exclusions = ExclusionSettings()
    settings.naukri.gmail_otp_email = ""
    settings.naukri.gmail_app_password = ""
    settings.naukri.email = "dev@example.com"

    settings.project_root = tmp_path
    settings.resumes_dir = (tmp_path / "resumes") if tmp_path is not None else None
    settings.ensure_dirs = MagicMock()

    for section, values in sections.items():
        target = getattr(settings, section)
        for key, value in values.items():
            setattr(target, key, value)
    return settings


def make_profile(**overrides) -> ResumeProfile:
    values = {
        "name": "Test User",
        "email": "dev@example.com",
        "current_title": "Java Developer",
        "summary": "Java developer with Spring Boot experience",
        "total_experience_years": 1.5,
        "skills": ["Java", "Spring Boot", "SQL"],
        "technical_skills": ["Java", "Spring Boot", "Hibernate", "MySQL"],
    }
    values.update(overrides)
    return ResumeProfile(**values)


def make_job(**overrides) -> Job:
    values = {
        "naukri_job_id": "job_1",
        "title": "Java Developer",
        "company": "Acme Corp",
        "url": "https://www.naukri.com/job-details-1",
        "location": "Bangalore",
        "experience": "0-2 Yrs",
        "salary": "8 LPA",
        "description": "Build Java Spring Boot services with MySQL.",
        "skills": "Java, Spring Boot, MySQL",
    }
    values.update(overrides)
    return Job(**values)


def java_job(job_id: str = "job_1", **overrides) -> Job:
    return make_job(naukri_job_id=job_id, **overrides)


def apply_job_details(
    description: str = "Java Spring Boot backend role with MySQL and Hibernate.",
    skills: str = "Java, Spring Boot",
    openings: int = 3,
    has_company_logo: bool = True,
) -> dict:
    return {
        "description": description,
        "skills": skills,
        "openings": openings,
        "has_company_logo": has_company_logo,
    }


def make_engine(page_url: str = "https://www.naukri.com/", is_alive: bool = True) -> MagicMock:
    engine = MagicMock(name="browser_engine")
    page = MagicMock(name="page")
    page.url = page_url
    page.goto = AsyncMock()
    engine.page = page
    engine.launch = AsyncMock()
    engine.close = AsyncMock()
    engine.is_alive = MagicMock(return_value=is_alive)
    engine.save_session = AsyncMock()
    return engine


def make_interactions() -> MagicMock:
    interactions = MagicMock(name="browser_interactions")
    interactions.action_delay = AsyncMock()
    interactions.wait_for_navigation_complete = AsyncMock()
    interactions.human_type = AsyncMock()
    interactions.safe_click = AsyncMock(return_value=True)
    return interactions


def make_repo(**overrides) -> MagicMock:
    repo = MagicMock(name="repository")

    def _save_job(**kwargs):
        return Job(id=next(_JOB_IDS), **kwargs)

    repo.initialize = AsyncMock()
    repo.create_run_log = AsyncMock(return_value=7)
    repo.update_run_log = AsyncMock()
    repo.get_all_job_descriptions = AsyncMock(return_value=[])
    repo.get_today_application_count = AsyncMock(return_value=0)
    repo.is_already_applied = MagicMock(return_value=False)
    repo.is_already_applied_composite = MagicMock(return_value=False)
    repo.save_job = AsyncMock(side_effect=_save_job)
    repo.save_application = AsyncMock(return_value=JobApplication(id=101))
    repo.begin_application = AsyncMock(return_value=55)
    repo.finalize_application = AsyncMock()
    repo.get_application_stats = AsyncMock(
        return_value={"total": 0, "applied": 0, "skipped": 0, "failed": 0}
    )
    repo.get_recent_applications = AsyncMock(return_value=[])
    repo.get_run_stats = AsyncMock(return_value=[])
    for key, value in overrides.items():
        setattr(repo, key, value)
    return repo


def make_parser(profile: ResumeProfile | None = _UNSET) -> MagicMock:
    parser = MagicMock(name="resume_parser")
    resolved = make_profile() if profile is _UNSET else profile
    parser.parse = AsyncMock(return_value=resolved)
    return parser


def make_parser_without_profile() -> MagicMock:
    """A resume parser that resolves to ``None`` (e.g. an unreadable PDF)."""
    return make_parser(profile=None)


def make_login(login_success: bool = True, last_error: str = "") -> MagicMock:
    login = MagicMock(name="login_handler")
    login.login = AsyncMock(return_value=login_success)
    login.last_error = last_error
    return login


def make_searcher(jobs: list[Job] | None = None, details: dict | None = None) -> MagicMock:
    searcher = MagicMock(name="job_searcher")
    searcher.search_all = AsyncMock(return_value=jobs if jobs is not None else [])
    searcher.get_job_description = AsyncMock(
        return_value=details if details is not None else apply_job_details()
    )
    return searcher


def make_matcher(result: JobApplication | None = _UNSET) -> MagicMock:
    matcher = MagicMock(name="job_matcher")
    resolved = JobApplication(match_score=88.0) if result is _UNSET else result
    matcher.match = AsyncMock(return_value=resolved)
    return matcher


def make_applier(status: str = "applied", **result_fields) -> MagicMock:
    applier = MagicMock(name="job_applier")
    applier.apply_to_job = AsyncMock(return_value={"status": status, **result_fields})
    return applier


def make_refresher() -> MagicMock:
    refresher = MagicMock(name="profile_refresher")
    refresher.refresh = AsyncMock(return_value=True)
    return refresher


def make_agent(
    tmp_path=None,
    *,
    settings=None,
    repository=None,
    browser_engine=None,
    browser_interactions=None,
    resume_parser=None,
    login_handler=None,
    job_searcher=None,
    job_matcher=None,
    question_answerer_factory=None,
    job_applier_factory=None,
    profile_refresher=None,
    **attributes,
) -> NaukriAgent:
    """Build a fully wired NaukriAgent with mocked collaborators."""
    settings = settings if settings is not None else make_settings(tmp_path)
    repository = repository if repository is not None else make_repo()
    engine = browser_engine if browser_engine is not None else make_engine()
    interactions = browser_interactions if browser_interactions is not None else make_interactions()
    parser = resume_parser if resume_parser is not None else make_parser()
    login = login_handler if login_handler is not None else make_login()
    searcher = job_searcher if job_searcher is not None else make_searcher()
    matcher = job_matcher if job_matcher is not None else make_matcher()
    refresher = profile_refresher if profile_refresher is not None else make_refresher()

    agent = NaukriAgent(
        settings=settings,
        repository=repository,
        browser_engine=engine,
        browser_interactions=interactions,
        llm_provider=MagicMock(name="llm"),
        resume_parser=parser,
        login_handler=login,
        job_searcher=searcher,
        job_matcher=matcher,
        question_answerer_factory=question_answerer_factory
        or (lambda profile: MagicMock(name="question_answerer")),
        job_applier_factory=job_applier_factory or (lambda qa: MagicMock(name="job_applier")),
        profile_refresher=refresher,
    )
    for key, value in attributes.items():
        setattr(agent, key, value)
    return agent


@contextlib.contextmanager
def quiet_async() -> Iterator[MagicMock]:
    """Neutralise logging setup, signal registration, sleeps and random delays."""
    with (
        patch("src.naukri_agent.bot.agent.setup_logging") as setup_logging,
        patch("src.naukri_agent.bot.agent.signal.signal"),
        patch("asyncio.sleep", new=AsyncMock()),
        patch(
            "src.naukri_agent.bot.agent.TimeUtility.random_delay",
            new=AsyncMock(return_value=0.0),
        ),
    ):
        yield setup_logging
