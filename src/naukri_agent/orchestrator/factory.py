"""
Dependency Injection factory for the Naukri Agent.
Centralizes the instantiation of all interfaces and services to enforce
the Dependency Inversion Principle.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.naukri_agent.ai.job_matcher import JobMatcher
from src.naukri_agent.ai.providers.gemini import GeminiProvider
from src.naukri_agent.ai.question_answerer import QuestionAnswerer
from src.naukri_agent.ai.resume_parser import ResumeParser
from src.naukri_agent.browser.apply import JobApplier
from src.naukri_agent.browser.engine import PlaywrightEngine
from src.naukri_agent.browser.interactions import HumanInteractions
from src.naukri_agent.browser.login import LoginHandler
from src.naukri_agent.browser.pages import JobDetailPage, LoginPage, SearchPage
from src.naukri_agent.browser.profile import ProfileRefresher
from src.naukri_agent.browser.search import JobSearcher
from src.naukri_agent.config.settings import Settings
from src.naukri_agent.core.interfaces import (
    IBrowserEngine,
    IBrowserInteractions,
    IJobMatcher,
    ILLMProvider,
    IQuestionAnswerer,
    IRepository,
    IResumeParser,
    IStealthPatcher,
    IOTPProvider,
    ILoginStrategy,
)
from src.naukri_agent.core.domain.entities import ResumeProfile
from src.naukri_agent.database.repository import SQLAlchemyRepository


class DependencyFactory:
    """Creates and wires dependencies for the application.

    A `session_factory` may be injected explicitly (recommended — see
    `src.main`, which creates one via `init_db()` and passes it in). If
    omitted, `get_repository()` will raise, since there is no implicit
    global database state to fall back on.
    """

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

        # Singletons
        self._llm_provider: ILLMProvider | None = None
        self._repository: IRepository | None = None
        self._browser_engine: IBrowserEngine | None = None
        self._browser_interactions: IBrowserInteractions | None = None
        self._stealth_patcher: IStealthPatcher | None = None
        self._otp_provider: IOTPProvider | None = None

    def get_settings(self) -> Settings:
        return self._settings

    def get_repository(self) -> IRepository:
        if not self._repository:
            if self._session_factory is None:
                raise RuntimeError(
                    "No database session factory configured. Call "
                    "`await init_db(settings.db_path)` and pass the result "
                    "to `DependencyFactory(settings, session_factory=...)`."
                )
            self._repository = SQLAlchemyRepository(self._session_factory)
        return self._repository

    def get_llm_provider(self) -> ILLMProvider:
        if not self._llm_provider:
            self._llm_provider = GeminiProvider(
                api_key=self._settings.ai.gemini_api_key,
                model_name=self._settings.ai.model,
            )
        return self._llm_provider

    def get_stealth_patcher(self) -> IStealthPatcher:
        if not self._stealth_patcher:
            from src.naukri_agent.browser.stealth import PlaywrightStealthPatcher

            self._stealth_patcher = PlaywrightStealthPatcher()
        return self._stealth_patcher

    def get_otp_provider(self) -> IOTPProvider | None:
        if not self._otp_provider:
            gmail_email = self._settings.naukri.gmail_otp_email
            gmail_password = self._settings.naukri.gmail_app_password
            if gmail_email and gmail_password:
                from src.naukri_agent.utils.gmail_otp import GmailOTPProvider

                self._otp_provider = GmailOTPProvider(
                    gmail_email=gmail_email,
                    app_password=gmail_password,
                )
        return self._otp_provider

    def get_browser_engine(self) -> IBrowserEngine:
        if not self._browser_engine:
            self._browser_engine = PlaywrightEngine(
                self._settings, stealth_patcher=self.get_stealth_patcher()
            )
        return self._browser_engine

    def get_browser_interactions(self) -> IBrowserInteractions:
        if not self._browser_interactions:
            engine = self.get_browser_engine()
            self._browser_interactions = HumanInteractions(engine, self._settings)
        return self._browser_interactions

    def create_resume_parser(self) -> IResumeParser:
        return ResumeParser(
            llm_provider=self.get_llm_provider(),
            repository=self.get_repository(),
            settings=self._settings,
        )

    def create_job_matcher(self) -> IJobMatcher:
        return JobMatcher(
            llm_provider=self.get_llm_provider(),
            settings=self._settings,
        )

    def create_question_answerer(self, resume_profile: ResumeProfile) -> IQuestionAnswerer:
        return QuestionAnswerer(
            llm_provider=self.get_llm_provider(),
            settings=self._settings,
            resume_profile=resume_profile,
        )

    def create_login_handler(self) -> LoginHandler:
        login_page = LoginPage(
            engine=self.get_browser_engine(),
            interactions=self.get_browser_interactions(),
        )

        strategy: ILoginStrategy
        if self._settings.naukri.use_otp_login:
            from src.naukri_agent.browser.login import OTPLoginStrategy

            strategy = OTPLoginStrategy(self._settings, self.get_otp_provider())
        else:
            from src.naukri_agent.browser.login import PasswordLoginStrategy

            strategy = PasswordLoginStrategy(self._settings, self.get_otp_provider())

        return LoginHandler(
            login_page=login_page,
            engine=self.get_browser_engine(),
            strategy=strategy,
        )

    def create_job_searcher(self) -> JobSearcher:
        search_page = SearchPage(
            engine=self.get_browser_engine(),
            interactions=self.get_browser_interactions(),
        )
        detail_page = JobDetailPage(
            engine=self.get_browser_engine(),
            interactions=self.get_browser_interactions(),
        )
        return JobSearcher(
            search_page=search_page,
            detail_page=detail_page,
            engine=self.get_browser_engine(),
            settings=self._settings,
        )

    def create_job_applier(self, question_answerer: IQuestionAnswerer) -> JobApplier:
        detail_page = JobDetailPage(
            engine=self.get_browser_engine(),
            interactions=self.get_browser_interactions(),
        )
        return JobApplier(
            detail_page=detail_page,
            settings=self._settings,
            question_answerer=question_answerer,
        )

    def create_profile_refresher(self) -> ProfileRefresher:
        return ProfileRefresher(
            engine=self.get_browser_engine(),
            interactions=self.get_browser_interactions(),
        )
