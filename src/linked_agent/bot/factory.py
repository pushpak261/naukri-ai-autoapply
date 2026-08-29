"""
Dependency Injection factory for the LinkedIn Agent.
Centralizes the instantiation of all interfaces and services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.linked_agent.database.manager import DatabaseManager

if TYPE_CHECKING:
    from src.naukri_agent.database.manager import DatabaseManager as NaukriDBManager

from src.linked_agent.ai.job_matcher import LinkedInJobMatcher
from src.linked_agent.ai.question_answerer import LinkedInQuestionAnswerer
from src.linked_agent.ai.resume_parser import LinkedInResumeParser
from src.linked_agent.browser.apply import LinkedInJobApplier
from src.linked_agent.browser.engine import LinkedInPlaywrightEngine
from src.linked_agent.browser.interactions import LinkedInHumanInteractions
from src.linked_agent.browser.login import LinkedInLoginHandler
from src.linked_agent.browser.pages import LinkedInLoginPage, LinkedInSearchPage, LinkedInJobDetailPage
from src.linked_agent.browser.search import LinkedInJobSearcher
from src.linked_agent.config.settings import Settings
from src.linked_agent.bot.interfaces import (
    IBrowserEngine,
    IBrowserInteractions,
    IJobMatcher,
    ILLMProvider,
    IQuestionAnswerer,
    IRepository,
    IResumeParser,
    IStealthPatcher,
)
from src.linked_agent.models.entities import ResumeProfile
from src.linked_agent.database.repository import SQLAlchemyRepository


class LinkedInDependencyFactory:
    """Creates and wires dependencies for the LinkedIn agent."""

    def __init__(
        self,
        settings: Settings,
        db_manager: DatabaseManager | None = None,
        naukri_db_manager: NaukriDBManager | None = None,
    ) -> None:
        self._settings = settings
        self._db_manager = db_manager
        self._naukri_db_manager = naukri_db_manager

        # Singletons
        self._llm_provider: ILLMProvider | None = None
        self._repository: IRepository | None = None
        self._browser_engine: IBrowserEngine | None = None
        self._browser_interactions: IBrowserInteractions | None = None
        self._stealth_patcher: IStealthPatcher | None = None

    def get_settings(self) -> Settings:
        return self._settings

    def get_repository(self) -> IRepository:
        if not self._repository:
            if self._db_manager is None:
                raise RuntimeError(
                    "No database manager configured. Call "
                    "`await setup_database_manager(settings.db_path)` and pass the result "
                    "to `LinkedInDependencyFactory(settings, db_manager=...)`."
                )
            self._repository = SQLAlchemyRepository(
                self._db_manager,
                naukri_db_manager=self._naukri_db_manager,
            )
        return self._repository

    def get_llm_provider(self) -> ILLMProvider:
        if not self._llm_provider:
            from src.linked_agent.ai.llm_provider import GeminiProvider
            self._llm_provider = GeminiProvider(
                api_key=self._settings.ai.gemini_api_key,
                model_name=self._settings.ai.model,
            )
        return self._llm_provider

    def get_stealth_patcher(self) -> IStealthPatcher:
        if not self._stealth_patcher:
            from src.linked_agent.browser.stealth import LinkedInStealthPatcher
            self._stealth_patcher = LinkedInStealthPatcher()
        return self._stealth_patcher

    def get_browser_engine(self) -> IBrowserEngine:
        if not self._browser_engine:
            self._browser_engine = LinkedInPlaywrightEngine(
                self._settings, stealth_patcher=self.get_stealth_patcher()
            )
        return self._browser_engine

    def get_browser_interactions(self) -> IBrowserInteractions:
        if not self._browser_interactions:
            engine = self.get_browser_engine()
            self._browser_interactions = LinkedInHumanInteractions(engine, self._settings)
        return self._browser_interactions

    def create_resume_parser(self) -> IResumeParser:
        return LinkedInResumeParser(
            llm_provider=self.get_llm_provider(),
            repository=self.get_repository(),
            settings=self._settings,
        )

    def create_job_matcher(self) -> IJobMatcher:
        return LinkedInJobMatcher(
            llm_provider=self.get_llm_provider(),
            settings=self._settings,
        )

    def create_question_answerer(self, resume_profile: ResumeProfile) -> IQuestionAnswerer:
        return LinkedInQuestionAnswerer(
            llm_provider=self.get_llm_provider(),
            settings=self._settings,
            resume_profile=resume_profile,
        )

    def create_login_handler(self) -> LinkedInLoginHandler:
        login_page = LinkedInLoginPage(
            engine=self.get_browser_engine(),
            interactions=self.get_browser_interactions(),
        )
        return LinkedInLoginHandler.create(
            login_page=login_page,
            engine=self.get_browser_engine(),
            settings=self._settings,
        )

    def create_job_searcher(self) -> LinkedInJobSearcher:
        search_page = LinkedInSearchPage(
            engine=self.get_browser_engine(),
            interactions=self.get_browser_interactions(),
        )
        detail_page = LinkedInJobDetailPage(
            engine=self.get_browser_engine(),
            interactions=self.get_browser_interactions(),
        )
        return LinkedInJobSearcher(
            search_page=search_page,
            detail_page=detail_page,
            engine=self.get_browser_engine(),
            settings=self._settings,
        )

    def create_job_applier(self, question_answerer: IQuestionAnswerer) -> LinkedInJobApplier:
        detail_page = LinkedInJobDetailPage(
            engine=self.get_browser_engine(),
            interactions=self.get_browser_interactions(),
        )
        return LinkedInJobApplier(
            detail_page=detail_page,
            settings=self._settings,
            question_answerer=question_answerer,
        )
