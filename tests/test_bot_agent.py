"""Unit tests for ``src.naukri_agent.bot.agent.NaukriAgent``.

All collaborators are mocked at their protocol boundary; no browser, SMTP,
network or real sleeping happens here.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from rich.panel import Panel
from rich.table import Table

from src.naukri_agent.bot.agent import NaukriAgent
from src.naukri_agent.config.constants import ApplicationStatus
from src.naukri_agent.models.entities import JobApplication
from tests.test_bot_agent_helpers import (
    StubPipeline,
    StubVectorFilter,
    apply_job_details,
    java_job,
    make_agent,
    make_applier,
    make_engine,
    make_interactions,
    make_job,
    make_matcher,
    make_parser,
    make_parser_without_profile,
    make_profile,
    make_repo,
    make_searcher,
    make_settings,
    quiet_async,
)

AGENT_MODULE = "src.naukri_agent.bot.agent"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _full_kwargs(**overrides):
    values = {
        "settings": make_settings(),
        "repository": make_repo(),
        "browser_engine": make_engine(),
        "browser_interactions": make_interactions(),
        "llm_provider": MagicMock(name="llm"),
        "resume_parser": make_parser(),
        "login_handler": MagicMock(name="login"),
        "job_searcher": make_searcher(),
        "job_matcher": make_matcher(),
        "question_answerer_factory": lambda profile: None,
        "job_applier_factory": lambda qa: None,
        "profile_refresher": MagicMock(name="refresher"),
    }
    values.update(overrides)
    return values


def _write_resume(tmp_path) -> str:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 fake")
    return str(resume)


@contextlib.contextmanager
def stub_process_jobs():
    with patch.object(NaukriAgent, "_process_jobs", new=AsyncMock()) as mocked:
        yield mocked


async def _process(
    agent,
    jobs,
    *,
    applier=None,
    searcher=None,
    matcher=None,
    vector_filter=None,
    pipeline=None,
):
    applier = applier if applier is not None else make_applier()
    searcher = searcher if searcher is not None else agent._job_searcher
    matcher = matcher if matcher is not None else agent._job_matcher
    vector_filter = vector_filter if vector_filter is not None else StubVectorFilter()
    agent._resume_profile = make_profile()
    if pipeline is not None:
        agent._pipeline = pipeline
    with quiet_async():
        await agent._process_jobs(jobs, matcher, applier, searcher, vector_filter)
    return applier, searcher, matcher, vector_filter


def _panel_text(console: MagicMock) -> list[str]:
    return [
        call.args[0].renderable
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], Panel)
    ]


def _tables(console: MagicMock) -> list[Table]:
    return [
        call.args[0]
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], Table)
    ]


def _row_values(table: Table) -> list[list[str]]:
    columns = [[str(cell) for cell in column._cells] for column in table.columns]
    return [list(row) for row in zip(*columns, strict=True)]


# ===========================================================================
# Constructor / dependency validation
# ===========================================================================


class TestConstructor:
    def test_requires_factory_or_settings(self):
        with pytest.raises(ValueError, match="Either factory or settings must be provided."):
            NaukriAgent()

    def test_settings_alone_is_not_enough(self):
        with pytest.raises(ValueError, match="Repository is required."):
            NaukriAgent(settings=make_settings())

    def test_repository_alone_is_not_enough(self):
        with pytest.raises(ValueError, match="Browser engine is required."):
            NaukriAgent(settings=make_settings(), repository=make_repo())

    @pytest.mark.parametrize(
        ("missing", "message"),
        [
            ("browser_interactions", "Browser interactions are required."),
            ("llm_provider", "LLM provider is required."),
            ("resume_parser", "Resume parser is required."),
            ("login_handler", "Login handler is required."),
            ("job_searcher", "Job searcher is required."),
            ("job_matcher", "Job matcher is required."),
            ("profile_refresher", "Profile refresher is required."),
        ],
    )
    def test_every_dependency_is_required(self, missing, message):
        kwargs = _full_kwargs()
        kwargs.pop(missing)
        with pytest.raises(ValueError, match=re.escape(message)):
            NaukriAgent(**kwargs)

    def test_question_answerer_factory_required(self):
        kwargs = _full_kwargs()
        kwargs.pop("question_answerer_factory")
        with pytest.raises(ValueError, match=re.escape("Question answerer factory is required.")):
            NaukriAgent(**kwargs)

    def test_job_applier_factory_required(self):
        kwargs = _full_kwargs()
        kwargs.pop("job_applier_factory")
        with pytest.raises(ValueError, match=re.escape("Job applier factory is required.")):
            NaukriAgent(**kwargs)

    def test_wires_everything_from_factory(self):
        settings = make_settings()
        profile = make_profile()
        factory = MagicMock(name="factory")
        factory.get_settings.return_value = settings
        factory.get_repository.return_value = make_repo()
        factory.get_browser_engine.return_value = make_engine()
        factory.get_browser_interactions.return_value = make_interactions()
        factory.get_llm_provider.return_value = MagicMock(name="llm")
        factory.create_resume_parser.return_value = make_parser()
        factory.create_login_handler.return_value = MagicMock(name="login")
        factory.create_job_searcher.return_value = make_searcher()
        factory.create_job_matcher.return_value = make_matcher()
        factory.create_profile_refresher.return_value = MagicMock(name="refresher")
        answerer = MagicMock(name="answerer")
        applier = MagicMock(name="applier")
        factory.create_question_answerer.return_value = answerer
        factory.create_job_applier.return_value = applier

        agent = NaukriAgent(factory)

        assert agent._settings is settings
        assert agent._repo is factory.get_repository.return_value
        assert agent._engine is factory.get_browser_engine.return_value
        assert agent._interactions is factory.get_browser_interactions.return_value
        assert agent._llm is factory.get_llm_provider.return_value
        assert agent._resume_parser is factory.create_resume_parser.return_value
        assert agent._login_handler is factory.create_login_handler.return_value
        assert agent._job_searcher is factory.create_job_searcher.return_value
        assert agent._job_matcher is factory.create_job_matcher.return_value
        assert agent._profile_refresher is factory.create_profile_refresher.return_value

        assert agent._question_answerer_factory(profile) is answerer
        factory.create_question_answerer.assert_called_once_with(profile)
        assert agent._job_applier_factory(answerer) is applier
        factory.create_job_applier.assert_called_once_with(answerer)

    def test_explicit_arguments_win_over_factory(self):
        custom_repo = make_repo()
        custom_engine = make_engine()
        factory = MagicMock(name="factory")
        factory.get_settings.return_value = make_settings()

        agent = NaukriAgent(
            factory,
            repository=custom_repo,
            browser_engine=custom_engine,
            browser_interactions=make_interactions(),
            llm_provider=MagicMock(name="llm"),
            resume_parser=make_parser(),
            login_handler=MagicMock(name="login"),
            job_searcher=make_searcher(),
            job_matcher=make_matcher(),
            question_answerer_factory=lambda profile: MagicMock(),
            job_applier_factory=lambda qa: MagicMock(),
            profile_refresher=MagicMock(name="refresher"),
        )

        assert agent._repo is custom_repo
        assert agent._engine is custom_engine
        factory.get_repository.assert_not_called()
        factory.get_browser_engine.assert_not_called()

    def test_initial_state(self):
        agent = NaukriAgent(**_full_kwargs())
        assert agent._resume_profile is None
        assert agent._run_log_id is None
        assert agent._interrupted is False
        assert agent._external_jobs == []
        assert agent._pipeline is None
        assert agent._jobs_found == 0
        assert agent._jobs_applied == 0
        assert agent._jobs_skipped == 0
        assert agent._jobs_failed == 0
        assert agent._daily_applied == 0


# ===========================================================================
# run()
# ===========================================================================


class TestRun:
    def _runnable(self, tmp_path, jobs=None, **sections):
        settings = make_settings(tmp_path, **sections)
        settings.resume.path = _write_resume(tmp_path)
        agent = make_agent(tmp_path, settings=settings, job_searcher=make_searcher(jobs=jobs))
        return agent

    async def test_full_run_applies_targeted_job(self, tmp_path):
        settings = make_settings(tmp_path, exclusions={"enable_scam_filter": True})
        settings.resume.path = _write_resume(tmp_path)
        searcher = make_searcher(
            jobs=[
                java_job("job_clean", company="Infosys Limited"),
                java_job(
                    "job_scam",
                    company="Bright Future Consultancy Services",
                    description="",
                ),
            ]
        )
        applier = make_applier(status=ApplicationStatus.APPLIED)
        repo = make_repo()
        agent = make_agent(
            tmp_path,
            settings=settings,
            repository=repo,
            job_searcher=searcher,
            job_applier_factory=lambda qa: applier,
        )

        with quiet_async():
            await agent.run()

        assert settings.application.dry_run is False
        repo.initialize.assert_awaited_once()
        repo.create_run_log.assert_awaited_once_with(search_keywords=["Java Developer"])
        agent._engine.launch.assert_awaited_once()
        agent._login_handler.login.assert_awaited_once()

        applied_job_ids = [c.args[0].naukri_job_id for c in applier.apply_to_job.await_args_list]
        assert applied_job_ids == ["job_clean"]
        assert agent._jobs_found == 2
        assert agent._jobs_applied == 1
        assert agent._jobs_failed == 0

        finalize_kwargs = repo.finalize_application.await_args.kwargs
        assert finalize_kwargs["status"] == ApplicationStatus.APPLIED

        repo.update_run_log.assert_awaited_once()
        update_kwargs = repo.update_run_log.await_args.kwargs
        assert update_kwargs["run_log_id"] == 7
        assert update_kwargs["jobs_found"] == 2
        assert update_kwargs["jobs_applied"] == 1
        assert update_kwargs["status"] == "completed"

        assert (tmp_path / "data" / "logs" / "metrics.json").exists()

    async def test_dry_run_flag_is_forced_on(self, tmp_path):
        agent = self._runnable(tmp_path, jobs=[java_job()])
        with quiet_async(), stub_process_jobs() as process:
            await agent.run(dry_run=True)
        assert agent._settings.application.dry_run is True
        process.assert_awaited_once()
        assert [j.naukri_job_id for j in process.await_args.args[0]] == ["job_1"]

    async def test_returns_when_resume_profile_missing(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.resume.path = _write_resume(tmp_path)
        agent = make_agent(tmp_path, settings=settings, resume_parser=make_parser_without_profile())
        with quiet_async(), stub_process_jobs() as process:
            await agent.run()
        agent._engine.launch.assert_not_awaited()
        process.assert_not_awaited()
        agent._engine.close.assert_awaited_once()

    async def test_login_failure_marks_agent_blocked(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.resume.path = _write_resume(tmp_path)
        login = MagicMock(name="login")
        login.login = AsyncMock(return_value=False)
        login.last_error = "Please verify you are human"
        agent = make_agent(tmp_path, settings=settings, login_handler=login)

        with (
            quiet_async(),
            patch("api.agent_runtime.mark_agent_blocked", new=AsyncMock()) as blocked,
            stub_process_jobs(),
        ):
            await agent.run()

        blocked.assert_awaited_once()
        assert blocked.await_args.args[1] == "captcha"
        assert blocked.await_args.args[2] is None
        agent._job_searcher.search_all.assert_not_awaited()

    async def test_login_failure_without_classifiable_block(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.resume.path = _write_resume(tmp_path)
        login = MagicMock(name="login")
        login.login = AsyncMock(return_value=False)
        login.last_error = ""
        agent = make_agent(tmp_path, settings=settings, login_handler=login)

        with (
            quiet_async(),
            patch("api.agent_runtime.mark_agent_blocked", new=AsyncMock()) as blocked,
            stub_process_jobs(),
        ):
            await agent.run()

        blocked.assert_not_awaited()
        agent._engine.close.assert_awaited_once()

    async def test_missing_login_handler_is_logged_and_cleaned_up(self, tmp_path):
        agent = self._runnable(tmp_path)
        agent._login_handler = None
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.run()
        log_error.assert_called_once_with("Agent error: LoginHandler not configured.")
        agent._engine.close.assert_awaited_once()

    async def test_missing_job_searcher_is_logged(self, tmp_path):
        agent = self._runnable(tmp_path)
        agent._job_searcher = None
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.run()
        log_error.assert_called_once_with("Agent error: JobSearcher not configured.")

    async def test_missing_job_matcher_is_logged(self, tmp_path):
        agent = self._runnable(tmp_path, jobs=[java_job()])
        agent._job_matcher = None
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.run()
        log_error.assert_called_once_with("Agent error: JobMatcher not configured.")

    async def test_missing_question_answerer_factory_is_logged(self, tmp_path):
        agent = self._runnable(tmp_path, jobs=[java_job()])
        agent._question_answerer_factory = None
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.run()
        log_error.assert_called_once_with("Agent error: QuestionAnswerer factory not configured.")

    async def test_missing_job_applier_factory_is_logged(self, tmp_path):
        agent = self._runnable(tmp_path, jobs=[java_job()])
        agent._job_applier_factory = None
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.run()
        log_error.assert_called_once_with("Agent error: JobApplier factory not configured.")

    async def test_guards_missing_resume_profile_after_search(self, tmp_path):
        agent = self._runnable(tmp_path)

        async def _search(*, should_stop=None):
            agent._resume_profile = None
            return [java_job()]

        agent._job_searcher.search_all = AsyncMock(side_effect=_search)
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.run()
        log_error.assert_called_once_with("Agent error: Resume profile not loaded.")

    async def test_interrupted_during_search_skips_evaluation(self, tmp_path):
        agent = self._runnable(tmp_path)

        async def _search(*, should_stop=None):
            agent._interrupted = True
            return [java_job()]

        agent._job_searcher.search_all = AsyncMock(side_effect=_search)
        repo = agent._repo
        with quiet_async(), stub_process_jobs() as process:
            await agent.run()

        process.assert_not_awaited()
        assert agent._jobs_found == 1
        assert repo.update_run_log.await_args.kwargs["jobs_found"] == 1
        assert repo.update_run_log.await_args.kwargs["status"] == "interrupted"

    async def test_no_jobs_found(self, tmp_path):
        agent = self._runnable(tmp_path)
        with (
            quiet_async(),
            patch(f"{AGENT_MODULE}.log_warning") as log_warning,
            stub_process_jobs() as process,
        ):
            await agent.run()
        process.assert_not_awaited()
        log_warning.assert_called_once_with("No jobs found matching your search criteria.")

    async def test_scam_filter_notifies_about_removed_jobs(self, tmp_path):
        settings = make_settings(
            tmp_path,
            exclusions={"enable_scam_filter": True},
            application={"email_notifications_enabled": True, "notify_on_scam": True},
        )
        settings.resume.path = _write_resume(tmp_path)
        searcher = make_searcher(
            jobs=[
                java_job(
                    "job_scam",
                    company="Bright Future Consultancy Services",
                    description="",
                ),
                java_job("job_clean", company="Infosys Limited"),
            ]
        )
        agent = make_agent(tmp_path, settings=settings, job_searcher=searcher)

        with (
            quiet_async(),
            stub_process_jobs() as process,
            patch(
                "src.naukri_agent.utils.notification.send_notification", new=AsyncMock()
            ) as notify,
        ):
            await agent.run()

        process.assert_awaited_once()
        surviving = process.await_args.args[0]
        assert [j.naukri_job_id for j in surviving] == ["job_clean"]
        assert agent._jobs_skipped == 1

        notify.assert_awaited_once()
        assert notify.await_args.args[1] == "scam.detected"
        assert "1 suspicious jobs removed" in notify.await_args.args[2]
        assert "Bright Future Consultancy Services" in notify.await_args.args[3]

    async def test_scam_filter_without_notifications(self, tmp_path):
        settings = make_settings(tmp_path, exclusions={"enable_scam_filter": True})
        settings.resume.path = _write_resume(tmp_path)
        searcher = make_searcher(
            jobs=[
                java_job(
                    "job_scam",
                    company="Bright Future Consultancy Services",
                    description="",
                ),
                java_job("job_clean", company="Infosys Limited"),
            ]
        )
        agent = make_agent(tmp_path, settings=settings, job_searcher=searcher)

        with (
            quiet_async(),
            stub_process_jobs() as process,
            patch(
                "src.naukri_agent.utils.notification.send_notification", new=AsyncMock()
            ) as notify,
        ):
            await agent.run()

        assert len(process.await_args.args[0]) == 1
        notify.assert_not_awaited()

    async def test_scam_filter_disabled_keeps_all_jobs(self, tmp_path):
        agent = self._runnable(tmp_path)
        searcher = make_searcher(
            jobs=[
                java_job("job_scam", company="Bright Future Consultancy Services"),
                java_job("job_clean", company="Infosys Limited"),
            ]
        )
        agent._job_searcher = searcher
        with quiet_async(), stub_process_jobs() as process:
            await agent.run()
        assert len(process.await_args.args[0]) == 2
        assert agent._pipeline.is_scam_filter_enabled is False
        assert agent._pipeline.exclusion_spec is not None

    async def test_doc_frequencies_built_from_repository_corpus(self, tmp_path):
        agent = self._runnable(tmp_path)
        agent._repo.get_all_job_descriptions = AsyncMock(
            return_value=["java spring boot", "java microservices", ""]
        )
        agent._job_searcher = make_searcher(jobs=[java_job()])
        with quiet_async(), stub_process_jobs() as process:
            await agent.run()

        vector_filter = process.await_args.args[4]
        assert vector_filter.total_documents == 3
        assert vector_filter.doc_frequencies["java"] == 2
        assert vector_filter.doc_frequencies["spring"] == 1
        assert vector_filter.doc_frequencies["boot"] == 1
        assert vector_filter.doc_frequencies["microservices"] == 1

    async def test_doc_frequency_failure_is_survivable(self, tmp_path):
        agent = self._runnable(tmp_path)
        agent._repo.get_all_job_descriptions = AsyncMock(side_effect=RuntimeError("db offline"))
        agent._job_searcher = make_searcher(jobs=[java_job()])
        with quiet_async(), stub_process_jobs() as process:
            await agent.run()
        vector_filter = process.await_args.args[4]
        assert vector_filter.total_documents == 0
        assert vector_filter.doc_frequencies == {}

    async def test_question_answerer_and_applier_factories_receive_dependencies(self, tmp_path):
        agent = self._runnable(tmp_path)
        answerer = MagicMock(name="answerer")
        applier = MagicMock(name="applier")
        qa_calls = []
        applier_calls = []
        agent._question_answerer_factory = lambda profile: (
            qa_calls.append(profile),
            answerer,
        )[1]
        agent._job_applier_factory = lambda qa: (applier_calls.append(qa), applier)[1]
        agent._job_searcher = make_searcher(jobs=[java_job()])

        with quiet_async(), stub_process_jobs():
            await agent.run()

        assert qa_calls == [agent._resume_profile]
        assert applier_calls == [answerer]

    async def test_keyboard_interrupt_marks_run_interrupted(self, tmp_path):
        agent = self._runnable(tmp_path)
        agent._engine.launch = AsyncMock(side_effect=KeyboardInterrupt())
        repo = agent._repo
        with quiet_async(), patch(f"{AGENT_MODULE}.log_warning") as log_warning:
            await agent.run()
        assert agent._interrupted is True
        assert repo.update_run_log.await_args.kwargs["status"] == "interrupted"
        assert "Agent interrupted by user (Ctrl+C)" in [
            call.args[0] for call in log_warning.call_args_list
        ]

    async def test_generic_error_is_logged_and_run_completes(self, tmp_path):
        agent = self._runnable(tmp_path)
        agent._engine.launch = AsyncMock(side_effect=RuntimeError("browser exploded"))
        repo = agent._repo
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.run()
        log_error.assert_called_once_with("Agent error: browser exploded")
        assert repo.update_run_log.await_args.kwargs["status"] == "completed"
        assert repo.update_run_log.await_args.kwargs["jobs_found"] == 0

    async def test_generic_error_after_interrupt_logs_graceful_shutdown(self, tmp_path):
        agent = self._runnable(tmp_path)
        agent._interrupted = True
        agent._engine.launch = AsyncMock(side_effect=RuntimeError("context closed"))
        with (
            quiet_async(),
            patch(f"{AGENT_MODULE}.log_warning") as log_warning,
            patch(f"{AGENT_MODULE}.log_error") as log_error,
        ):
            await agent.run()
        log_error.assert_not_called()
        log_warning.assert_called_once_with(
            "Agent run interrupted during browser operation. Shutting down gracefully."
        )

    async def test_setup_logging_and_signal_registration(self, tmp_path):
        agent = self._runnable(tmp_path)
        agent._job_searcher = make_searcher(jobs=[])
        with (
            patch(f"{AGENT_MODULE}.setup_logging") as setup_logging,
            patch(f"{AGENT_MODULE}.signal.signal") as signal_signal,
            stub_process_jobs(),
        ):
            await agent.run()
        setup_logging.assert_called_once_with(
            level="INFO", log_to_file=False, log_dir=str(tmp_path / "data" / "logs")
        )
        assert signal_signal.call_count >= 1
        agent._settings.ensure_dirs.assert_called_once()


# ===========================================================================
# _parse_resume
# ===========================================================================


class TestParseResume:
    def _settings_with_resume(self, tmp_path, resume_path=None):
        settings = make_settings(tmp_path)
        settings.resumes_dir = tmp_path / "resumes"
        settings.resumes_dir.mkdir(parents=True, exist_ok=True)
        settings.resume.path = resume_path
        return settings

    async def test_uses_uploaded_resume_from_profile_json(self, tmp_path):
        (tmp_path / "resumes").mkdir()
        uploaded = tmp_path / "resumes" / "uploaded.pdf"
        uploaded.write_bytes(b"%PDF-1.4")
        (tmp_path / "resume_profile.json").write_text(
            json.dumps({"uploaded_file_path": str(uploaded)}), encoding="utf-8"
        )
        settings = self._settings_with_resume(tmp_path, resume_path="unused.pdf")
        parser = make_parser()
        agent = make_agent(tmp_path, settings=settings, resume_parser=parser)

        await agent._parse_resume()

        parser.parse.assert_awaited_once_with(str(uploaded))
        assert agent._resume_profile is parser.parse.return_value

    async def test_uploaded_path_outside_resumes_dir_is_ignored(self, tmp_path):
        outside = tmp_path / "evil.pdf"
        outside.write_bytes(b"%PDF-1.4")
        fallback = _write_resume(tmp_path)
        (tmp_path / "resume_profile.json").write_text(
            json.dumps({"uploaded_file_path": str(outside)}), encoding="utf-8"
        )
        settings = self._settings_with_resume(tmp_path, resume_path=fallback)
        parser = make_parser()
        agent = make_agent(tmp_path, settings=settings, resume_parser=parser)

        await agent._parse_resume()

        parser.parse.assert_awaited_once_with(fallback)

    async def test_invalid_profile_json_falls_back(self, tmp_path):
        (tmp_path / "resume_profile.json").write_text("{not json", encoding="utf-8")
        fallback = _write_resume(tmp_path)
        settings = self._settings_with_resume(tmp_path, resume_path=fallback)
        parser = make_parser()
        agent = make_agent(tmp_path, settings=settings, resume_parser=parser)

        await agent._parse_resume()

        parser.parse.assert_awaited_once_with(fallback)

    async def test_profile_json_without_uploaded_path_falls_back(self, tmp_path):
        (tmp_path / "resume_profile.json").write_text(
            json.dumps({"name": "Someone"}), encoding="utf-8"
        )
        fallback = _write_resume(tmp_path)
        settings = self._settings_with_resume(tmp_path, resume_path=fallback)
        parser = make_parser()
        agent = make_agent(tmp_path, settings=settings, resume_parser=parser)

        await agent._parse_resume()

        parser.parse.assert_awaited_once_with(fallback)

    async def test_missing_uploaded_file_falls_back(self, tmp_path):
        (tmp_path / "resume_profile.json").write_text(
            json.dumps({"uploaded_file_path": str(tmp_path / "resumes" / "gone.pdf")}),
            encoding="utf-8",
        )
        fallback = _write_resume(tmp_path)
        settings = self._settings_with_resume(tmp_path, resume_path=fallback)
        parser = make_parser()
        agent = make_agent(tmp_path, settings=settings, resume_parser=parser)

        await agent._parse_resume()

        parser.parse.assert_awaited_once_with(fallback)

    async def test_relative_resume_path_is_resolved_against_project_root(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "cv.pdf").write_bytes(b"%PDF-1.4")
        settings = self._settings_with_resume(tmp_path, resume_path="data/cv.pdf")
        parser = make_parser()
        agent = make_agent(tmp_path, settings=settings, resume_parser=parser)

        await agent._parse_resume()

        parser.parse.assert_awaited_once_with(str(tmp_path / "data" / "cv.pdf"))

    async def test_no_resume_path_configured(self, tmp_path):
        settings = self._settings_with_resume(tmp_path, resume_path="")
        parser = make_parser()
        agent = make_agent(tmp_path, settings=settings, resume_parser=parser)

        await agent._parse_resume()

        parser.parse.assert_not_awaited()
        assert agent._resume_profile is None

    async def test_resume_file_missing(self, tmp_path):
        settings = self._settings_with_resume(tmp_path, resume_path=str(tmp_path / "nope.pdf"))
        parser = make_parser()
        agent = make_agent(tmp_path, settings=settings, resume_parser=parser)

        await agent._parse_resume()

        parser.parse.assert_not_awaited()
        assert agent._resume_profile is None

    async def test_parser_result_is_rendered(self, tmp_path):
        fallback = _write_resume(tmp_path)
        settings = self._settings_with_resume(tmp_path, resume_path=fallback)
        profile = make_profile(name="Alice", total_experience_years=1.5)
        agent = make_agent(tmp_path, settings=settings, resume_parser=make_parser(profile=profile))

        with patch(f"{AGENT_MODULE}.console") as console:
            await agent._parse_resume()

        rendered = _panel_text(console)
        assert len(rendered) == 1
        assert "Alice" in rendered[0]
        assert "Java" in rendered[0]
        assert "1.5 years" in rendered[0]

    async def test_missing_parser_raises(self, tmp_path):
        fallback = _write_resume(tmp_path)
        settings = self._settings_with_resume(tmp_path, resume_path=fallback)
        agent = make_agent(tmp_path, settings=settings)
        agent._resume_parser = None

        with pytest.raises(RuntimeError, match="ResumeParser not configured."):
            await agent._parse_resume()


# ===========================================================================
# _process_jobs
# ===========================================================================


class TestProcessJobsQueue:
    async def test_requires_resume_profile(self):
        agent = make_agent()
        with pytest.raises(AssertionError):
            await agent._process_jobs(
                [java_job()],
                make_matcher(),
                make_applier(),
                make_searcher(),
                StubVectorFilter(),
            )

    async def test_applies_job_and_records_daily_count(self):
        agent = make_agent()
        applier, _, _, _ = await _process(agent, [java_job()])

        assert agent._jobs_applied == 1
        assert agent._jobs_skipped == 0
        assert agent._jobs_failed == 0
        assert agent._daily_applied == 1
        assert applier.apply_to_job.await_args.args[0].naukri_job_id == "job_1"

    async def test_save_job_receives_full_job_payload(self):
        agent = make_agent()
        repo = agent._repo
        job = java_job(openings=4, has_company_logo=True, posted_date="Just Now")
        await _process(agent, [job])

        save_kwargs = repo.save_job.await_args.kwargs
        assert save_kwargs["naukri_job_id"] == "job_1"
        assert save_kwargs["title"] == "Java Developer"
        assert save_kwargs["openings"] == 4
        assert save_kwargs["has_company_logo"] is True
        assert save_kwargs["posted_date"] == "Just Now"

    async def test_heuristics_disabled_scores_are_zero(self):
        agent = make_agent()
        applier, _, _, _ = await _process(agent, [java_job()])
        assert applier.apply_to_job.await_count == 1
        assert agent._jobs_applied == 1

    async def test_heuristics_apply_boosts(self, tmp_path, caplog):
        settings = make_settings(tmp_path, search={"enable_heuristics": True})
        agent = make_agent(tmp_path, settings=settings)
        job = java_job(title="Java Developer", posted_date="Just Now")
        vector_filter = StubVectorFilter(score=0.5)

        with caplog.at_level(logging.INFO, logger=AGENT_MODULE):
            await _process(agent, [job], vector_filter=vector_filter)

        assert vector_filter.calls == ["Java Developer Acme Corp Java, Spring Boot, MySQL"]
        queue_messages = [
            r.getMessage() for r in caplog.records if "Priority Queue" in r.getMessage()
        ]
        assert len(queue_messages) == 1
        assert "Score: 0.85" in queue_messages[0]
        assert "Java Developer @ Acme Corp" in queue_messages[0]

    async def test_heuristics_two_day_freshness_boost(self, tmp_path, caplog):
        settings = make_settings(tmp_path, search={"enable_heuristics": True})
        agent = make_agent(tmp_path, settings=settings)
        job = java_job(
            title="Zookeeper", skills="Zoo", posted_date="2 days ago", experience="3-5 Yrs"
        )
        vector_filter = StubVectorFilter(score=0.5)

        with caplog.at_level(logging.INFO, logger=AGENT_MODULE):
            await _process(agent, [job], vector_filter=vector_filter)

        queue_messages = [
            r.getMessage() for r in caplog.records if "Priority Queue" in r.getMessage()
        ]
        assert "Score: 0.55" in queue_messages[0]
        assert agent._jobs_skipped == 1
        assert agent._jobs_applied == 0

    async def test_heuristics_skip_below_minimum_score(self, tmp_path):
        settings = make_settings(tmp_path, search={"enable_heuristics": True})
        agent = make_agent(tmp_path, settings=settings)
        job = java_job(title="Zookeeper", skills="Zoo", posted_date="")
        vector_filter = StubVectorFilter(score=0.0)

        applier, _, _, _ = await _process(agent, [job], vector_filter=vector_filter)

        assert vector_filter.calls == ["Zookeeper Acme Corp Zoo"]
        assert agent._jobs_skipped == 1
        assert applier.apply_to_job.await_count == 0

    async def test_excluded_at_scrape_time(self):
        agent = make_agent()
        pipeline = StubPipeline(excluded=True)
        applier, _, _, _ = await _process(agent, [java_job()], pipeline=pipeline)

        assert agent._jobs_skipped == 1
        assert pipeline.is_excluded_calls == [("job_1", 0.0)]
        assert applier.apply_to_job.await_count == 0

    async def test_excluded_after_queueing(self):
        agent = make_agent()
        pipeline = StubPipeline(excluded=[False, True])
        applier, _, _, _ = await _process(agent, [java_job()], pipeline=pipeline)

        assert agent._jobs_skipped == 1
        assert applier.apply_to_job.await_count == 0
        assert len(pipeline.is_excluded_calls) == 2

    async def test_interrupted_before_loop_body(self):
        agent = make_agent()
        agent._interrupted = True
        applier, _, _, _ = await _process(agent, [java_job()])

        assert applier.apply_to_job.await_count == 0
        assert agent._jobs_applied == 0

    async def test_daily_cap_reached_before_first_job(self):
        settings = make_settings(application={"daily_cap": 3})
        agent = make_agent(settings=settings)
        agent._repo.get_today_application_count = AsyncMock(return_value=3)
        applier, _, _, _ = await _process(agent, [java_job()])

        assert applier.apply_to_job.await_count == 0
        assert agent._jobs_applied == 0

    async def test_daily_cap_reached_midway(self):
        settings = make_settings(application={"daily_cap": 1})
        agent = make_agent(settings=settings)
        agent._repo.get_today_application_count = AsyncMock(side_effect=[0, 0, 1])
        applier, _, _, _ = await _process(agent, [java_job("job_1"), java_job("job_2")])

        assert applier.apply_to_job.await_count == 1
        assert agent._jobs_applied == 1

    async def test_duplicate_by_job_id_is_skipped(self):
        agent = make_agent()
        agent._repo.is_already_applied = MagicMock(return_value=True)
        applier, _, _, _ = await _process(agent, [java_job()])

        assert agent._jobs_skipped == 1
        assert applier.apply_to_job.await_count == 0

    async def test_duplicate_by_title_company_is_skipped(self):
        agent = make_agent()
        agent._repo.is_already_applied_composite = MagicMock(return_value=True)
        applier, _, _, _ = await _process(agent, [java_job()])

        assert agent._jobs_skipped == 1
        assert applier.apply_to_job.await_count == 0


class TestProcessJobsBrowser:
    async def test_restarts_dead_browser_and_logs_in_again(self):
        engine = make_engine(is_alive=False)
        agent = make_agent(browser_engine=engine)
        applier, _, _, _ = await _process(agent, [java_job()])

        engine.is_alive.assert_called_once()
        engine.close.assert_awaited_once()
        engine.launch.assert_awaited_once()
        agent._login_handler.login.assert_awaited_once()
        assert applier.apply_to_job.await_count == 1
        assert agent._jobs_applied == 1

    async def test_browser_close_error_during_restart_is_suppressed(self):
        engine = make_engine(is_alive=False)
        engine.close = AsyncMock(side_effect=PlaywrightTimeoutError("already closed"))
        agent = make_agent(browser_engine=engine)
        applier, _, _, _ = await _process(agent, [java_job()])

        engine.launch.assert_awaited_once()
        assert applier.apply_to_job.await_count == 1

    async def test_relogin_failure_after_restart_is_logged_and_continues(self):
        engine = make_engine(is_alive=False)
        login = MagicMock(name="login")
        login.login = AsyncMock(side_effect=PlaywrightError("nope"))
        agent = make_agent(browser_engine=engine, login_handler=login)

        with quiet_async(), patch(f"{AGENT_MODULE}.logger") as logger:
            await _process(agent, [java_job()])

        logger.error.assert_called_once_with("Failed to re-login after restart: nope")

    async def test_missing_login_handler_during_restart_raises(self):
        engine = make_engine(is_alive=False)
        agent = make_agent(browser_engine=engine)
        agent._login_handler = None
        with pytest.raises(RuntimeError, match="LoginHandler not configured."):
            await _process(agent, [java_job()])

    async def test_description_is_fetched_when_missing(self):
        agent = make_agent()
        job = java_job(description="", skills="")
        searcher = make_searcher(
            details=apply_job_details(
                description="Java Spring Boot role", skills="Java, Spring", openings=7
            )
        )
        applier, _, _, _ = await _process(agent, [job], searcher=searcher)

        searcher.get_job_description.assert_awaited_once_with(job.url)
        assert job.description == "Java Spring Boot role"
        assert job.skills == "Java, Spring"
        assert job.openings == 7
        agent._interactions.action_delay.assert_awaited_once()
        assert applier.apply_to_job.await_count == 1

    async def test_description_fetch_defaults(self):
        agent = make_agent()
        job = java_job(description="", skills="")
        searcher = make_searcher(details={})
        await _process(agent, [job], searcher=searcher)

        assert job.description == ""
        assert job.openings == 0
        assert job.has_company_logo is False
        assert job.skills == ""

    async def test_missing_interactions_raises(self):
        agent = make_agent()
        job = java_job(description="")
        agent._interactions = None
        with pytest.raises(RuntimeError, match="BrowserInteractions not configured."):
            await _process(agent, [job])

    async def test_missing_interactions_after_navigation_raises(self):
        engine = make_engine(page_url="https://www.naukri.com/jobs")
        agent = make_agent(browser_engine=engine)
        agent._interactions = None
        job = java_job(url="https://www.naukri.com/job-details-77")
        with pytest.raises(RuntimeError, match="BrowserInteractions not configured."):
            await _process(agent, [job])
        engine.page.goto.assert_awaited_once_with(
            job.url, wait_until="domcontentloaded", timeout=60000
        )

    async def test_excluded_after_description_fetch(self):
        agent = make_agent()
        job = java_job(description="")
        pipeline = StubPipeline(excluded=[False, False, True])
        searcher = make_searcher()
        applier, _, _, _ = await _process(agent, [job], pipeline=pipeline, searcher=searcher)

        assert agent._jobs_skipped == 1
        assert applier.apply_to_job.await_count == 0
        assert len(pipeline.is_excluded_calls) == 3

    async def test_deep_scam_check_skips_and_notifies(self):
        settings = make_settings(
            exclusions={"enable_scam_filter": True},
            application={"email_notifications_enabled": True, "notify_on_scam": True},
        )
        agent = make_agent(settings=settings)
        pipeline = StubPipeline(deep_scam=True)
        job = java_job(description="")

        with patch(
            "src.naukri_agent.utils.notification.send_notification", new=AsyncMock()
        ) as notify:
            applier, _, _, _ = await _process(
                agent, [job], pipeline=pipeline, searcher=make_searcher()
            )

        assert agent._jobs_skipped == 1
        assert applier.apply_to_job.await_count == 0
        assert pipeline.deep_scam_calls == ["job_1"]
        notify.assert_awaited_once()
        assert notify.await_args.args[1] == "scam.detected"
        assert "Java Developer @ Acme Corp" in notify.await_args.args[2]
        assert job.url in notify.await_args.args[3]

    async def test_deep_scam_check_without_notifications(self):
        settings = make_settings(exclusions={"enable_scam_filter": True})
        agent = make_agent(settings=settings)
        pipeline = StubPipeline(deep_scam=True)

        with patch(
            "src.naukri_agent.utils.notification.send_notification", new=AsyncMock()
        ) as notify:
            await _process(
                agent,
                [java_job(description="")],
                pipeline=pipeline,
                searcher=make_searcher(),
            )

        assert agent._jobs_skipped == 1
        notify.assert_not_awaited()

    async def test_non_matching_domain_is_skipped(self):
        agent = make_agent()
        job = java_job(title="QA Analyst")
        applier, _, _, _ = await _process(agent, [job])

        assert agent._jobs_skipped == 1
        assert applier.apply_to_job.await_count == 0

    async def test_targeting_gate_rejects_senior_role(self):
        agent = make_agent()
        job = java_job(experience="5-8 Yrs")
        applier, _, _, _ = await _process(agent, [job])

        assert agent._jobs_skipped == 1
        assert applier.apply_to_job.await_count == 0

    async def test_targeting_gate_rejects_non_java_stack(self):
        agent = make_agent()
        job = java_job(title="Python Developer", skills="Python", description="Python code")
        applier, _, _, _ = await _process(agent, [job])

        assert agent._jobs_skipped == 1
        assert applier.apply_to_job.await_count == 0

    async def test_navigates_when_job_url_is_not_open(self):
        engine = make_engine(page_url="https://www.naukri.com/jobs")
        agent = make_agent(browser_engine=engine)
        job = java_job(url="https://www.naukri.com/job-details-42")
        applier, _, _, _ = await _process(agent, [job])

        engine.page.goto.assert_awaited_once_with(
            job.url, wait_until="domcontentloaded", timeout=60000
        )
        agent._interactions.wait_for_navigation_complete.assert_awaited_once()
        assert applier.apply_to_job.await_count == 1

    async def test_no_navigation_when_job_url_already_open(self):
        url = "https://www.naukri.com/job-details-42"
        engine = make_engine(page_url=url)
        agent = make_agent(browser_engine=engine)
        await _process(agent, [java_job(url=url)])

        engine.page.goto.assert_not_awaited()

    async def test_navigation_failure_records_failed_application(self):
        engine = make_engine(page_url="https://www.naukri.com/jobs")
        engine.page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("timeout"))
        agent = make_agent(browser_engine=engine)
        repo = agent._repo
        applier, _, _, _ = await _process(
            agent, [java_job(url="https://www.naukri.com/job-details-42")]
        )

        assert applier.apply_to_job.await_count == 0
        assert agent._jobs_failed == 1
        save_kwargs = repo.save_application.await_args.kwargs
        assert save_kwargs["status"] == ApplicationStatus.FAILED
        assert save_kwargs["error_message"].startswith("Navigation failed: ")
        repo.begin_application.assert_not_awaited()

    async def test_domain_override_marks_job_skipped_low_score(self, monkeypatch):
        agent = make_agent()
        repo = agent._repo
        responses = iter([False, True])
        monkeypatch.setattr(
            NaukriAgent,
            "_is_job_in_excluded_domain",
            staticmethod(lambda job: next(responses)),
        )

        applier, _, _, _ = await _process(agent, [java_job()])

        assert applier.apply_to_job.await_count == 0
        assert agent._jobs_skipped == 1
        save_kwargs = repo.save_application.await_args.kwargs
        assert save_kwargs["status"] == ApplicationStatus.SKIPPED_LOW_SCORE
        assert save_kwargs["match_score"] == 40.0

    async def test_dry_run_records_skipped_dry_run(self):
        settings = make_settings(application={"dry_run": True})
        agent = make_agent(settings=settings)
        repo = agent._repo
        applier, _, _, _ = await _process(agent, [java_job()])

        assert applier.apply_to_job.await_count == 0
        assert agent._jobs_skipped == 1
        save_kwargs = repo.save_application.await_args.kwargs
        assert save_kwargs["status"] == ApplicationStatus.SKIPPED_DRY_RUN
        assert save_kwargs["match_score"] == 100.0
        repo.begin_application.assert_not_awaited()

    async def test_matcher_is_never_called(self):
        agent = make_agent()
        matcher = make_matcher()
        applier, _, _, _ = await _process(agent, [java_job()], matcher=matcher)

        matcher.match.assert_not_called()
        assert applier.apply_to_job.await_count == 1


class TestProcessJobsPersistence:
    async def test_claimed_application_is_finalized(self):
        agent = make_agent()
        repo = agent._repo
        await _process(agent, [java_job()])

        repo.begin_application.assert_awaited_once()
        claim_kwargs = repo.begin_application.await_args.kwargs
        assert claim_kwargs["match_score"] == 100.0
        assert claim_kwargs["match_reasoning"] == (
            "Java/Spring role within 0-2 yrs target (targeting gate)"
        )
        finalize_kwargs = repo.finalize_application.await_args.kwargs
        assert finalize_kwargs["app_id"] == 55
        assert finalize_kwargs["status"] == ApplicationStatus.APPLIED
        assert finalize_kwargs["error_message"] == ""
        repo.save_application.assert_not_awaited()

    async def test_unclaimed_application_is_saved_directly(self):
        agent = make_agent()
        repo = agent._repo
        repo.begin_application = AsyncMock(return_value=None)
        await _process(agent, [java_job()])

        repo.finalize_application.assert_not_awaited()
        save_kwargs = repo.save_application.await_args.kwargs
        assert save_kwargs["status"] == ApplicationStatus.APPLIED
        assert save_kwargs["match_score"] == 100.0

    async def test_external_status_collects_external_url(self):
        agent = make_agent()
        job = java_job()
        applier = make_applier(
            status=ApplicationStatus.SKIPPED_EXTERNAL,
            external_url="https://careers.example.com/apply",
        )
        await _process(agent, [job], applier=applier)

        assert agent._jobs_skipped == 1
        assert agent._jobs_applied == 0
        assert agent._external_jobs == [(job, "https://careers.example.com/apply")]

    async def test_screening_skipped_without_pdf_stays_collected(self):
        settings = make_settings(application={"answer_questions_with_pdf": True})
        agent = make_agent(settings=settings)
        job = java_job()
        applier = make_applier(status=ApplicationStatus.SKIPPED_SCREENING)
        await _process(agent, [job], applier=applier)

        assert agent._jobs_skipped == 1
        assert agent._external_jobs == []

    async def test_screening_skipped_without_pdf_is_emailed(self):
        settings = make_settings(application={"answer_questions_with_pdf": False})
        agent = make_agent(settings=settings)
        job = java_job()
        applier = make_applier(status=ApplicationStatus.SKIPPED_SCREENING)
        await _process(agent, [job], applier=applier)

        assert agent._jobs_skipped == 1
        assert agent._external_jobs == [(job, None)]

    async def test_failed_status_is_recorded(self):
        settings = make_settings(application={"collect_external_jobs": False})
        agent = make_agent(settings=settings)
        job = java_job()
        applier = make_applier(status=ApplicationStatus.FAILED, error_message="boom")
        await _process(agent, [job], applier=applier)

        assert agent._jobs_failed == 1
        assert agent._external_jobs == []
        finalize_kwargs = agent._repo.finalize_application.await_args.kwargs
        assert finalize_kwargs["status"] == ApplicationStatus.FAILED
        assert finalize_kwargs["error_message"] == "boom"

    async def test_failed_status_collects_external_job(self):
        settings = make_settings(application={"collect_external_jobs": True})
        agent = make_agent(settings=settings)
        job = java_job()
        applier = make_applier(status=ApplicationStatus.FAILED, error_message="boom")
        await _process(agent, [job], applier=applier)

        assert agent._jobs_failed == 1
        assert agent._external_jobs == [(job, None)]

    async def test_missing_status_defaults_to_failed(self):
        settings = make_settings(application={"collect_external_jobs": True})
        agent = make_agent(settings=settings)
        job = java_job()
        applier = MagicMock(name="job_applier")
        applier.apply_to_job = AsyncMock(return_value={})
        await _process(agent, [job], applier=applier)

        assert agent._jobs_failed == 1
        finalize_kwargs = agent._repo.finalize_application.await_args.kwargs
        assert finalize_kwargs["status"] == ApplicationStatus.FAILED
        assert finalize_kwargs["error_message"] == ""

    async def test_external_block_stops_the_loop(self):
        agent = make_agent()
        repo = agent._repo
        job = java_job()
        applier = make_applier(
            status=ApplicationStatus.FAILED,
            error_message="Please solve the captcha to continue",
        )

        with patch("api.agent_runtime.mark_agent_blocked", new=AsyncMock()) as blocked:
            await _process(agent, [job, java_job("job_2")], applier=applier)

        blocked.assert_awaited_once()
        assert blocked.await_args.args[1] == "captcha"
        assert blocked.await_args.args[2] is job
        assert applier.apply_to_job.await_count == 1
        assert agent._jobs_failed == 1
        finalize_kwargs = repo.finalize_application.await_args.kwargs
        assert finalize_kwargs["status"] == "failed"
        assert finalize_kwargs["error_message"].startswith("External block (captcha): ")

    async def test_external_block_detected_from_status(self):
        agent = make_agent()
        applier = make_applier(status="too many requests")
        with patch("api.agent_runtime.mark_agent_blocked", new=AsyncMock()) as blocked:
            await _process(agent, [java_job()], applier=applier)

        assert blocked.await_args.args[1] == "ip_ban"
        assert agent._jobs_failed == 1


# ===========================================================================
# _passes_targeting / _is_job_in_excluded_domain
# ===========================================================================


class TestTargeting:
    def test_java_role_without_experience_passes(self):
        agent = make_agent()
        ok, reason = agent._passes_targeting(java_job(experience=""))
        assert ok is True
        assert reason == "Java/Spring role within 0-2 yrs at a real company"

    def test_single_number_experience_is_parsed(self):
        agent = make_agent()
        ok, reason = agent._passes_targeting(java_job(experience="1 Yrs"))
        assert ok is True
        assert reason == "Java/Spring role within 0-2 yrs at a real company"

    def test_month_named_experience_skips_numeric_parsing(self):
        agent = make_agent()
        ok, _ = agent._passes_targeting(java_job(experience="Jan 2023 - Dec 2024"))
        assert ok is True

    def test_experience_above_ceiling(self):
        agent = make_agent()
        ok, reason = agent._passes_targeting(java_job(experience="4-6 Yrs"))
        assert ok is False
        assert reason == "Experience required (4 Yrs) exceeds 2 Yrs target"

    def test_senior_range_rejected_even_within_ceiling(self):
        settings = make_settings(search={"experience_max": 10})
        agent = make_agent(settings=settings)
        ok, reason = agent._passes_targeting(java_job(experience="3-5 Yrs"))
        assert ok is False
        assert reason == "Senior role (3-5 Yrs) exceeds 10 Yrs target"

    def test_non_java_stack_rejected(self):
        agent = make_agent()
        ok, reason = agent._passes_targeting(
            java_job(title="Python Developer", skills="Python", description="Python")
        )
        assert ok is False
        assert reason == "No Java/Spring stack found in title, skills, or description"

    def test_excluded_domain_helper(self):
        assert NaukriAgent._is_job_in_excluded_domain(java_job(title="Data Entry Operator")) is True
        assert NaukriAgent._is_job_in_excluded_domain(java_job(title="Java Developer")) is (False)
        assert NaukriAgent._is_job_in_excluded_domain(java_job(title="")) is False


# ===========================================================================
# _cleanup
# ===========================================================================


class TestCleanup:
    async def test_updates_run_log_and_records_metrics(self, tmp_path):
        settings = make_settings(tmp_path)
        agent = make_agent(tmp_path, settings=settings)
        repo = agent._repo
        agent._run_log_id = 7
        agent._jobs_found = 5
        agent._jobs_applied = 2
        agent._jobs_skipped = 1
        agent._jobs_failed = 1

        with quiet_async():
            await agent._cleanup()

        repo.update_run_log.assert_awaited_once_with(
            run_log_id=7,
            jobs_found=5,
            jobs_applied=2,
            jobs_skipped=1,
            jobs_failed=1,
            status="completed",
        )
        agent._engine.close.assert_awaited_once()

        metrics = json.loads(
            (tmp_path / "data" / "logs" / "metrics.json").read_text(encoding="utf-8")
        )
        assert metrics["total_runs"] == 1
        assert metrics["jobs_applied"] == 2
        assert metrics["jobs_failed"] == 1

    async def test_interrupted_run_log_status(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        agent._run_log_id = 9
        agent._interrupted = True
        with quiet_async():
            await agent._cleanup()
        assert agent._repo.update_run_log.await_args.kwargs["status"] == "interrupted"

    async def test_no_run_log_update_without_run_id(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        with quiet_async():
            await agent._cleanup()
        agent._repo.update_run_log.assert_not_awaited()

    async def test_external_jobs_email_is_sent(self, tmp_path):
        settings = make_settings(tmp_path, application={"collect_external_jobs": True})
        agent = make_agent(tmp_path, settings=settings)
        job = java_job()
        agent._external_jobs = [(job, "https://careers.example.com")]

        with (
            quiet_async(),
            patch("src.naukri_agent.utils.email_sender.send_external_jobs_email") as send_email,
        ):
            await agent._cleanup()

        send_email.assert_called_once_with([(job, "https://careers.example.com")], settings)

    async def test_external_jobs_email_failure_is_swallowed(self, tmp_path):
        settings = make_settings(tmp_path, application={"collect_external_jobs": True})
        agent = make_agent(tmp_path, settings=settings)
        agent._external_jobs = [(java_job(), None)]

        with (
            quiet_async(),
            patch(
                "src.naukri_agent.utils.email_sender.send_external_jobs_email",
                side_effect=RuntimeError("smtp down"),
            ),
            patch(f"{AGENT_MODULE}.logger") as logger,
        ):
            await agent._cleanup()

        logger.error.assert_called_once_with("Failed to send external jobs email: smtp down")

    async def test_email_not_sent_when_disabled(self, tmp_path):
        settings = make_settings(tmp_path, application={"collect_external_jobs": False})
        agent = make_agent(tmp_path, settings=settings)
        agent._external_jobs = [(java_job(), None)]

        with (
            quiet_async(),
            patch("src.naukri_agent.utils.email_sender.send_external_jobs_email") as send_email,
        ):
            await agent._cleanup()

        send_email.assert_not_called()

    async def test_browser_close_error_is_swallowed(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        agent._engine.close = AsyncMock(side_effect=PlaywrightError("gone"))
        with quiet_async(), patch(f"{AGENT_MODULE}.logger") as logger:
            await agent._cleanup()
        logger.debug.assert_called_once_with("Browser close error: gone")


# ===========================================================================
# Rendering helpers
# ===========================================================================


class TestRendering:
    def test_banner_contains_settings(self):
        settings = make_settings(
            search={"keywords": ["Java", "Spring"], "locations": ["Pune"]},
            application={"daily_cap": 7, "match_score_threshold": 55},
            ai={"enable_matching": False, "model": "gemini-3.5-flash"},
        )
        agent = make_agent(settings=settings)
        with patch(f"{AGENT_MODULE}.console") as console:
            agent._print_banner()
        rendered = _panel_text(console)[0]
        assert "Keywords: Java, Spring" in rendered
        assert "Locations: Pune" in rendered
        assert "Daily Cap: 7" in rendered
        assert "Match Threshold: 55%" in rendered
        assert "AI Matching: Disabled (Bulk Apply Mode)" in rendered
        assert "Dry Run: No" in rendered
        assert "AI Model: gemini-3.5-flash" in rendered

    def test_banner_shows_dry_run_and_ai(self):
        settings = make_settings(ai={"enable_matching": True})
        agent = make_agent(settings=settings)
        agent._settings.application.dry_run = True
        with patch(f"{AGENT_MODULE}.console") as console:
            agent._print_banner()
        rendered = _panel_text(console)[0]
        assert "AI Matching: Enabled" in rendered
        assert "Dry Run: Yes" in rendered

    def test_summary_table_uses_counters(self):
        agent = make_agent()
        agent._jobs_found = 11
        agent._jobs_applied = 4
        agent._jobs_skipped = 6
        agent._jobs_failed = 1
        with patch(f"{AGENT_MODULE}.console") as console:
            agent._print_summary()
        rows = _row_values(_tables(console)[0])
        assert rows == [
            ["Jobs Found", "11"],
            ["Jobs Applied", "[bold green]4[/bold green]"],
            ["Jobs Skipped", "6"],
            ["Jobs Failed", "1"],
        ]


class TestSignalHandlers:
    def test_posix_registers_int_and_term(self, monkeypatch):
        agent = make_agent()
        monkeypatch.setattr("sys.platform", "linux")
        with patch(f"{AGENT_MODULE}.signal.signal") as signal_signal:
            agent._register_signal_handlers()
        registered = [call.args[0] for call in signal_signal.call_args_list]
        assert registered == [
            __import__("signal").SIGINT,
            __import__("signal").SIGTERM,
        ]

    def test_windows_registers_only_sigint(self, monkeypatch):
        agent = make_agent()
        monkeypatch.setattr("sys.platform", "win32")
        with patch(f"{AGENT_MODULE}.signal.signal") as signal_signal:
            agent._register_signal_handlers()
        registered = [call.args[0] for call in signal_signal.call_args_list]
        assert registered == [__import__("signal").SIGINT]

    def test_handler_sets_interrupted_flag(self, monkeypatch):
        agent = make_agent()
        monkeypatch.setattr("sys.platform", "win32")
        with patch(f"{AGENT_MODULE}.signal.signal") as signal_signal:
            agent._register_signal_handlers()
        handler = signal_signal.call_args.args[1]
        assert agent._interrupted is False
        with patch(f"{AGENT_MODULE}.log_warning") as log_warning:
            handler(__import__("signal").SIGINT, None)
        assert agent._interrupted is True
        log_warning.assert_called_once_with("Received shutdown signal. Cleaning up...")


# ===========================================================================
# Public utility commands
# ===========================================================================


class TestParseResumeOnly:
    async def test_returns_and_prints_profile(self):
        profile = make_profile(name="Bob", skills=["Java"])
        parser = make_parser(profile=profile)
        agent = make_agent(resume_parser=parser)

        with patch(f"{AGENT_MODULE}.console") as console:
            result = await agent.parse_resume_only("resume.pdf")

        assert result is profile
        parser.parse.assert_awaited_once_with("resume.pdf")
        printed = json.loads(console.print_json.call_args.args[0])
        assert printed["name"] == "Bob"
        assert printed["skills"] == ["Java"]

    async def test_returns_none_when_parser_returns_none(self):
        agent = make_agent(resume_parser=make_parser_without_profile())
        with patch(f"{AGENT_MODULE}.console") as console:
            assert await agent.parse_resume_only("resume.pdf") is None
        console.print_json.assert_not_called()

    async def test_missing_parser_raises(self):
        agent = make_agent()
        agent._resume_parser = None
        with pytest.raises(RuntimeError, match="ResumeParser not configured."):
            await agent.parse_resume_only("resume.pdf")


class TestTestMatch:
    def _agent(self, tmp_path, details=None, **agent_kwargs):
        settings = make_settings(tmp_path)
        settings.resume.path = _write_resume(tmp_path)
        return make_agent(tmp_path, settings=settings, **agent_kwargs)

    async def test_scores_job_url(self, tmp_path):
        details = {
            "description": "Java Spring Boot",
            "skills": "Java",
            "location_detail": "Pune",
            "experience_detail": "0-2 Yrs",
            "salary_detail": "9 LPA",
        }
        searcher = make_searcher(details=details)
        result = JobApplication(
            match_score=91.0, should_apply=True, applied_at="2026-01-02T03:04:05"
        )
        matcher = make_matcher(result=result)
        agent = self._agent(tmp_path, job_searcher=searcher, job_matcher=matcher)

        with patch(f"{AGENT_MODULE}.console") as console:
            returned = await agent.test_match("https://www.naukri.com/job-details-9")

        assert returned is result
        agent._engine.launch.assert_awaited_once()
        agent._engine.close.assert_awaited_once()
        searcher.get_job_description.assert_awaited_once_with(
            "https://www.naukri.com/job-details-9"
        )
        scored_job = matcher.match.await_args.args[1]
        assert scored_job.naukri_job_id == "test_job"
        assert scored_job.title == "Test Job"
        assert scored_job.company == "Test Company"
        assert scored_job.description == "Java Spring Boot"
        assert scored_job.location == "Pune"
        assert scored_job.experience == "0-2 Yrs"
        assert scored_job.salary == "9 LPA"
        assert printed_score(console) == 91.0

    async def test_datetime_result_is_serialized_via_default_str(self, tmp_path):
        """A real ``JobApplication`` carries a datetime ``applied_at``.

        ``test_match`` json-dumps the dataclass, so the encoder needs
        ``default=str`` or the command raises TypeError for every result the
        production matcher can return.
        """
        searcher = make_searcher(details={})
        result = JobApplication(match_score=91.0, applied_at=datetime(2026, 1, 2, 3, 4, 5))
        matcher = make_matcher(result=result)
        agent = self._agent(tmp_path, job_searcher=searcher, job_matcher=matcher)

        with patch(f"{AGENT_MODULE}.console") as console:
            returned = await agent.test_match("https://www.naukri.com/job-details-9")

        assert returned is result
        payload = console.print_json.call_args.args[0]
        assert json.loads(payload)["applied_at"] == "2026-01-02 03:04:05"

    async def test_resume_failure_returns_none(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.resume.path = _write_resume(tmp_path)
        agent = make_agent(tmp_path, settings=settings, resume_parser=make_parser_without_profile())
        assert await agent.test_match("https://www.naukri.com/job-details-9") is None
        agent._engine.launch.assert_not_awaited()

    async def test_login_failure_closes_browser(self, tmp_path):
        login = MagicMock(name="login")
        login.login = AsyncMock(return_value=False)
        agent = self._agent(tmp_path, login_handler=login)
        with patch(f"{AGENT_MODULE}.log_error") as log_error:
            assert await agent.test_match("https://x/job") is None
        log_error.assert_called_once_with("Login failed")
        agent._engine.close.assert_awaited_once()

    async def test_missing_login_handler_raises(self, tmp_path):
        agent = self._agent(tmp_path)
        agent._login_handler = None
        with pytest.raises(RuntimeError, match="LoginHandler not configured."):
            await agent.test_match("https://x/job")

    async def test_missing_job_searcher_raises(self, tmp_path):
        agent = self._agent(tmp_path)
        agent._job_searcher = None
        with pytest.raises(RuntimeError, match="JobSearcher not configured."):
            await agent.test_match("https://x/job")

    async def test_missing_job_matcher_raises(self, tmp_path):
        agent = self._agent(tmp_path)
        agent._job_matcher = None
        with pytest.raises(RuntimeError, match="JobMatcher not configured."):
            await agent.test_match("https://x/job")


def printed_score(console: MagicMock) -> float:
    return json.loads(console.print_json.call_args.args[0])["match_score"]


class TestShowStatus:
    async def test_renders_stats_recent_and_runs(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        repo = agent._repo
        repo.get_application_stats = AsyncMock(
            return_value={"total": 9, "applied": 5, "skipped": 3, "failed": 1}
        )
        repo.get_recent_applications = AsyncMock(
            return_value=[
                {
                    "job_title": "Java Developer",
                    "company": "Acme",
                    "match_score": 88.0,
                    "status": "applied",
                    "applied_at": "2026-01-02T03:04:05",
                },
                {
                    "job_title": "Spring Developer",
                    "company": "Beta",
                    "match_score": 65.0,
                    "status": "skipped",
                    "applied_at": "2026-01-03T00:00:00",
                },
                {
                    "job_title": "Java Intern",
                    "company": "Gamma",
                    "match_score": 10.0,
                    "status": "failed",
                    "applied_at": None,
                },
            ]
        )
        repo.get_run_stats = AsyncMock(
            return_value=[
                {
                    "started_at": "2026-01-02T03:04:05",
                    "keywords": "Java Developer",
                    "found": 4,
                    "applied": 2,
                    "skipped": 1,
                    "status": "completed",
                },
                {
                    "started_at": None,
                    "keywords": "Spring Boot",
                    "found": 0,
                    "applied": 0,
                    "skipped": 0,
                    "status": "interrupted",
                },
            ]
        )

        with (
            patch(f"{AGENT_MODULE}.setup_logging") as setup_logging,
            patch(f"{AGENT_MODULE}.console") as console,
        ):
            await agent.show_status()

        setup_logging.assert_called_once_with(level="INFO", log_to_file=False)
        repo.initialize.assert_awaited_once()
        repo.get_application_stats.assert_awaited_once_with(days=7)
        repo.get_recent_applications.assert_awaited_once_with(limit=15)
        repo.get_run_stats.assert_awaited_once_with(limit=5)

        tables = _tables(console)
        assert len(tables) == 3
        assert _row_values(tables[0]) == [
            ["Total", "9"],
            ["Applied", "5"],
            ["Skipped", "3"],
            ["Failed", "1"],
        ]
        recent_rows = _row_values(tables[1])
        assert [row[0] for row in recent_rows] == [
            "Java Developer",
            "Spring Developer",
            "Java Intern",
        ]
        assert recent_rows[0][2] == "[green]88[/green]"
        assert recent_rows[1][2] == "[yellow]65[/yellow]"
        assert recent_rows[2][2] == "[red]10[/red]"
        assert recent_rows[2][4] == ""
        run_rows = _row_values(tables[2])
        assert run_rows[0][0] == "2026-01-02T03:04"
        assert run_rows[1][0] == ""

    async def test_renders_empty_sections_without_repository(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        agent._repo = None
        with (
            patch(f"{AGENT_MODULE}.setup_logging"),
            patch(f"{AGENT_MODULE}.console") as console,
        ):
            await agent.show_status()

        tables = _tables(console)
        assert len(tables) == 1
        assert _row_values(tables[0]) == [
            ["Total", "0"],
            ["Applied", "0"],
            ["Skipped", "0"],
            ["Failed", "0"],
        ]

    async def test_skips_empty_recent_and_runs(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        with (
            patch(f"{AGENT_MODULE}.setup_logging"),
            patch(f"{AGENT_MODULE}.console") as console,
        ):
            await agent.show_status()
        assert len(_tables(console)) == 1


class TestRefreshProfile:
    async def test_refreshes_profile_after_login(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        refresher = agent._profile_refresher
        with quiet_async():
            await agent.refresh_profile()
        agent._engine.launch.assert_awaited_once()
        agent._login_handler.login.assert_awaited_once()
        refresher.refresh.assert_awaited_once()
        agent._engine.close.assert_awaited_once()

    async def test_login_failure_skips_refresh(self, tmp_path):
        login = MagicMock(name="login")
        login.login = AsyncMock(return_value=False)
        agent = make_agent(tmp_path, settings=make_settings(tmp_path), login_handler=login)
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.refresh_profile()
        log_error.assert_called_once_with("Login failed. Cannot proceed with profile refresh.")
        agent._profile_refresher.refresh.assert_not_awaited()
        agent._engine.close.assert_awaited_once()

    async def test_missing_login_handler_is_logged(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        agent._login_handler = None
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.refresh_profile()
        log_error.assert_called_once_with(
            "Error during profile refresh task: LoginHandler not configured."
        )
        agent._engine.close.assert_awaited_once()

    async def test_missing_profile_refresher_is_logged(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        agent._profile_refresher = None
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.refresh_profile()
        log_error.assert_called_once_with(
            "Error during profile refresh task: ProfileRefresher not configured."
        )
        agent._engine.close.assert_awaited_once()

    async def test_keyboard_interrupt_is_handled(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        agent._engine.launch = AsyncMock(side_effect=KeyboardInterrupt())
        with quiet_async(), patch(f"{AGENT_MODULE}.log_warning") as log_warning:
            await agent.refresh_profile()
        assert agent._interrupted is True
        assert "Task interrupted by user (Ctrl+C)" in [
            call.args[0] for call in log_warning.call_args_list
        ]
        agent._engine.close.assert_awaited_once()

    async def test_generic_error_is_logged(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        agent._engine.launch = AsyncMock(side_effect=RuntimeError("no browser"))
        with quiet_async(), patch(f"{AGENT_MODULE}.log_error") as log_error:
            await agent.refresh_profile()
        log_error.assert_called_once_with("Error during profile refresh task: no browser")
        agent._engine.close.assert_awaited_once()

    async def test_browser_close_error_is_swallowed(self, tmp_path):
        agent = make_agent(tmp_path, settings=make_settings(tmp_path))
        agent._engine.close = AsyncMock(side_effect=PlaywrightTimeoutError("gone"))
        with quiet_async(), patch(f"{AGENT_MODULE}.logger") as logger:
            await agent.refresh_profile()
        logger.debug.assert_called_once_with("Browser close error: gone")
