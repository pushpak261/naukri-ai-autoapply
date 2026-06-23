# Implementation Plan: Comprehensive NFR Fulfillment

This document outlines the architectural changes and additions required to fulfill all 10 Non-Functional Requirements requested for the AI Naukri Agent.

## User Review Required

> [!IMPORTANT]
> The database migration from synchronous SQLite (`sqlite3`) to asynchronous SQLite (`aiosqlite`) requires adding `aiosqlite` to `requirements.txt` and refactoring `src/database/repository.py` to use `AsyncSession`. Since existing SQLite files will still work, no data loss will occur, but code will be significantly modified.
> 
> The core loop in `agent.py` will be rewritten to use an `asyncio.Queue` (Producer-Consumer) instead of a linear array to improve concurrency and **Scalability**.

## Open Questions

1. Do you want to receive system notifications (e.g., desktop popup) when the agent needs human intervention (e.g., CAPTCHA detected), as part of **Observability**?
2. Are you open to replacing `sqlite` with `PostgreSQL` in the future for better **Scalability**, or should we strictly optimize for `aiosqlite` right now?
3. Should we integrate Discord/Slack webhook alerting for **Observability**, or stick to local log files and console output?

---

## Proposed Changes

### 1. Performance (Fast Response Times) & 2. Scalability (Handle Growth)

We will migrate the database layer to be fully asynchronous to prevent I/O blocking, and optimize Playwright to skip loading unnecessary assets.

#### [MODIFY] src/database/models.py
- Update SQLAlchemy engine to use `sqlite+aiosqlite:///`.
- Enable connection pooling (`NullPool` or small `QueuePool` for async).

#### [MODIFY] src/database/repository.py
- Refactor all methods to `async def`.
- Replace `sessionmaker(bind=engine)` with `async_sessionmaker(bind=async_engine)`.
- Use `await session.execute(...)` instead of `.query()`.

#### [MODIFY] src/browser/engine.py
- Add `page.route("**/*", handler)` to block loading of images, fonts, and stylesheets to drastically reduce bandwidth and speed up scraping.

#### [MODIFY] src/orchestrator/agent.py
- Refactor `_process_jobs` to use `asyncio.Queue`. 
- **Producer task**: Fetch descriptions and push to AI evaluation queue.
- **Consumer tasks**: Evaluate with AI and apply to jobs concurrently.

---

### 3. Availability (High Uptime) & 8. Fault Tolerance (Survive Failures)

We will implement robust retries and a Circuit Breaker pattern to prevent the bot from crashing during temporary network/Naukri outages.

#### [MODIFY] requirements.txt
- Add `tenacity>=8.0.0` for retry logic.

#### [NEW] src/core/resilience.py
- Implement a `@retry_with_backoff` decorator using `tenacity` for Gemini API calls and network requests.
- Implement a `CircuitBreaker` class to halt operations if >5 consecutive errors occur (e.g., DOM structure changed).

#### [MODIFY] src/browser/engine.py
- Add automatic screenshots on unhandled exceptions: `await page.screenshot(path=f"data/logs/error_{time}.png")`.

---

### 4. Reliability (Correct & Consistent Behavior) & 10. Data Integrity

Ensure no partial data is written to the database and that AI outputs strictly follow expected formats.

#### [MODIFY] src/database/repository.py
- Wrap critical DB writes (like saving a job + application) in explicit `async with session.begin():` context managers for strict transaction isolation and rollback on failure.

#### [NEW] src/database/backup.py
- Create a script that automatically copies the `jobs.db` to `jobs_backup_{date}.db` before the agent starts a run, ensuring rollback capability in case of DB corruption.

#### [MODIFY] src/ai/providers/gemini.py
- Ensure Gemini output strictly conforms to Pydantic models by using `response_schema` in the `generate_content` call, preventing JSON parsing errors.

---

### 5. Security (Protect Data & Access)

#### [MODIFY] src/utils/logger.py
- Add a custom `Filter` to the Python logger that scrubs common PII patterns (emails, passwords, API keys) before writing to the log file or console.

#### [MODIFY] src/browser/engine.py
- Validate that `--disable-web-security` is NOT used, and enhance Playwright stealth arguments to prevent bot detection.

---

### 6. Maintainability (Easy to Modify) & 7. Extensibility (Add New Features)

#### [NEW] Makefile (or scripts/format.py)
- Add standard commands: `make format` (black, isort), `make lint` (ruff), `make typecheck` (mypy) to enforce code quality.

#### [NEW] src/core/interfaces.py
- Extract an `IAIProvider` base class and `IJobBoardProvider` base class, explicitly defining methods so future developers can easily add OpenAI, Anthropic, or LinkedIn support.

#### [MODIFY] src/orchestrator/agent.py
- Decouple `NaukriAgent` into a generic `JobApplicationAgent` that accepts any `IJobBoardProvider`.

---

### 9. Observability (Logging, Monitoring, Alerting)

#### [NEW] src/utils/telemetry.py
- Implement a `MetricsTracker` to record:
  - Total runtime duration.
  - API tokens consumed.
  - Application success vs failure rates.
- Save this to `data/logs/metrics.json` at the end of each run for historical monitoring.

#### [MODIFY] src/main.py
- Add a `--metrics` flag to `run` and `status` commands to view historical performance trends.

---

## Verification Plan

### Automated Tests
- Run existing `pytest` suite after the `aiosqlite` refactoring.
- Add unit tests for `resilience.py` (mock API failures to ensure retry kicks in).
- Add tests for `logger.py` to ensure PII is scrubbed.

### Manual Verification
- Run `python -m src.main run --dry-run` to ensure the asynchronous queue processes jobs without hanging.
- Verify `data/logs/error_*.png` is generated by artificially throwing an exception in the Playwright flow.
- Verify `metrics.json` is generated at the end of the run.
