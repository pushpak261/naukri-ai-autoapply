"""Backward-compatible re-exports after package layout refactor."""

from src.naukri_agent.bot.interfaces import (
    IBrowserEngine,
    IBrowserInteractions,
    IJobFilter,
    IJobMatcher,
    ILLMProvider,
    ILoginStrategy,
    IOTPProvider,
    IProgressReporter,
    IQuestionAnswerer,
    IRepository,
    IResumeParser,
    IStealthPatcher,
)

__all__ = [
    "IBrowserEngine",
    "IBrowserInteractions",
    "IJobFilter",
    "IJobMatcher",
    "ILLMProvider",
    "ILoginStrategy",
    "IOTPProvider",
    "IProgressReporter",
    "IQuestionAnswerer",
    "IRepository",
    "IResumeParser",
    "IStealthPatcher",
]
