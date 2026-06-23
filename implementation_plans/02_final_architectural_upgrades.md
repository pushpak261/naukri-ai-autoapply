# Implementation Plan: Final Architectural Upgrades

This plan outlines the steps to explicitly incorporate the missing architectural concepts: **Concurrency & Parallelism**, **Async Programming** (for LLMs), **Exception Handling**, **Logging & Monitoring** (Metrics), and additional **Caching**.

## Open Questions
- Do you want the Job Match Cache to persist across sessions (saved to disk like QACache) or just be an in-memory cache for the current run? (Plan assumes persistent JSON cache on disk).

## Proposed Changes

### 1. Async Programming, Concurrency & Parallelism

Currently, the `ILLMProvider` is synchronous. We will make it fully asynchronous to unblock the event loop and allow parallel AI requests.

#### [MODIFY] `src/core/interfaces.py`
- Change `generate_content` in `ILLMProvider` to an `async def` method.

#### [MODIFY] `src/ai/providers/gemini.py`
- Update `GeminiProvider` to use the asynchronous client `self._client.aio.models.generate_content`.

#### [MODIFY] `src/orchestrator/agent.py`
- **Concurrency Implementation**: Instead of processing jobs one-by-one sequentially, we will batch them. We will fetch job descriptions for a batch of jobs sequentially (browser limitation), and then use `asyncio.gather` to run `matcher.match()` on the entire batch **in parallel**.

### 2. Exception Handling (OOPS & SOLID)

We will replace generic `Exception` catches with a custom hierarchy of exceptions to improve error handling and debuggability.

#### [NEW] `src/core/exceptions.py`
Create custom exception classes:
- `AgentException` (Base)
- `LLMAPIError`
- `BrowserAutomationError`
- `DatabaseOperationError`

#### [MODIFY] `src/ai/providers/gemini.py`
- Catch API errors and wrap them in `LLMAPIError`.

#### [MODIFY] `src/browser/engine.py` & `src/browser/interactions.py`
- Raise `BrowserAutomationError` where critical failures occur instead of swallowing them or raising generic `RuntimeError`.

### 3. Caching (Performance)

We already cache Resume parsing and QA answers. We will add a persistent cache for Job Match scoring to save AI API tokens across different agent runs.

#### [MODIFY] `src/ai/job_matcher.py`
- Introduce a `MatchCache` class (similar to `QACache`) that saves `(resume_hash, job_id) -> match_result`.
- Check this cache before calling `generate_content`.

### 4. Logging & Monitoring

We will enhance the existing logging to include performance metrics (execution time) for the concurrent AI evaluations.

#### [MODIFY] `src/orchestrator/agent.py`
- Use `time.perf_counter()` to measure and log the time taken for parallel job evaluations.

## Verification Plan
1. **Syntax Check**: `python -m compileall src/`
2. **Dry Run**: Execute a dry run to verify that parallel job matching correctly uses `asyncio.gather` and successfully evaluates multiple jobs simultaneously.
