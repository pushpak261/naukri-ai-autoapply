# Code Review & Refactor Summary

This document records what was found and changed during the production-readiness
review of this codebase. Everything below was verified by actually running the
code (compiling, linting, type-checking, and running the test suite) — not just
read through.

## Starting point

The architecture was already solid: dependency-injected factory, `Protocol`-based
interfaces (`src/core/interfaces.py`), Pydantic settings, async SQLAlchemy,
Resilience4j-style retry/circuit-breaker patterns (`src/core/resilience.py`), and
an existing test suite. This was not a from-scratch rewrite — it was a hardening
pass on a codebase that already had good bones.

## Bugs found and fixed (verified, not theoretical)

1. **Crash on every match log** — `log_match()` in `src/utils/logger.py` didn't
   accept the `should_apply` keyword argument that `job_matcher.py` called it
   with. Every successful job match would have raised `TypeError`. Fixed the
   signature and the call site.

2. **Silent data-loss bug in the resume cache** — `SQLAlchemyRepository.save_resume_profile()`
   called `session.refresh(existing)` immediately after mutating `existing.parsed_json`,
   *before* the change was flushed. `session.refresh()` discards unflushed
   in-memory changes and reloads stale data from the DB — verified with a
   minimal repro script. The practical effect: once a resume was parsed once,
   **the cached AI-parsed profile would never update again**, even after editing
   the resume and re-running `parse-resume`. Removed the unnecessary `refresh()`
   call (the session factory already uses `expire_on_commit=False`, so it
   wasn't needed).

3. **Test suite didn't run at all** — `tests/test_database.py` imported a class
   (`Repository`) that doesn't exist; the real class is `SQLAlchemyRepository`.
   This was a hard pytest collection error that blocked **all 38 tests** from
   running, not just the database ones. Rewrote the file as proper async tests
   against the real `init_db()` / `SQLAlchemyRepository` API (using a real
   temp-file SQLite DB per test, not mocks — this is what caught bug #2 above).

4. **Three more broken tests** — `test_job_matcher.py` and `test_resume_parser.py`
   called `JobMatcher(mock_settings)` / `ResumeParser(mock_settings)` with one
   positional argument; the real constructors require `(llm_provider, settings)`
   / `(llm_provider, repository, settings)`. They also patched
   `"src.ai.job_matcher.genai"`, a module attribute that doesn't exist there
   (Gemini's SDK is only imported in `src/ai/providers/gemini.py`). Rewrote
   these tests to mock the actual `ILLMProvider` interface and added real
   `async` tests that exercise `match()` end-to-end, including a malformed-JSON
   path.

5. **Wrong assertion** — `test_sort_by_date` asserted `"sort=date" in url`, but
   the implementation correctly uses Naukri's actual query parameter (`sort=r`).
   The test was wrong, not the code; fixed the assertion.

6. **Latent `NameError` risk** — `orchestrator/agent.py` used `Any` in type
   hints without importing it (only safe because of `from __future__ import
   annotations` deferring evaluation — but would break under
   `typing.get_type_hints()` or stricter tooling). Cleaned up along with several
   imports that were done inline mid-function instead of at module level.

7. **Unhelpful error on Gemini safety blocks** — `GeminiProvider.generate_content()`
   called `response.text.strip()` without checking for `None`. When Gemini
   blocks a response (safety filters, token limits), `response.text` is `None`,
   producing a confusing `'NoneType' object has no attribute 'strip'` wrapped
   in a generic `LLMAPIError`. Added an explicit check that surfaces the actual
   `finish_reason` instead.

## Security / hygiene

- **The uploaded zip contained a live `.env`** with a real Naukri password and
  Gemini API key, plus SQLite DB backups, session cookies, and log files. None
  of these are in the delivered package — `.gitignore` was hardened to prevent
  them from being committed in the future (DB backups, AI response caches,
  coverage reports, `resume.pdf`).
- Removed `fix_resume.py` and `scrape_login.py` — one-off debug scripts left in
  the repo root, one of which had a hardcoded fake profile with your real name
  in it. Not part of the application; not something that belongs in a
  production-grade deliverable.
- Added `SECURITY.md` covering credential handling and — importantly — an
  explicit, upfront note that this agent's browser-fingerprint-spoofing
  (`src/browser/stealth.py`) almost certainly violates Naukri's Terms of
  Service and carries real account-ban risk. This isn't a code-quality issue
  refactoring can fix; it's a decision you should make with full information.

## Architecture changes

- **Removed a module-level mutable global** in `src/database/models.py`
  (`_AsyncSession` / `get_session_factory()`). `init_db()` now returns a fresh
  session factory with no shared global state; `DependencyFactory` takes it as
  an explicit constructor argument. This was previously the kind of pattern
  that breaks under parallel test runs or multiple agent instances in one
  process — it's also just harder to reason about than explicit dependency
  injection, which the rest of the codebase already used consistently.
- Settings: added `Settings.validate_required()`, called once at the start of
  `main.py run`, so missing credentials/resume/API key fail immediately with a
  clear, actionable message instead of a confusing error two layers down
  inside browser-login or AI code.

## Code quality

- Ran `ruff` (pyflakes/bugbear/simplify/pyupgrade/comprehensions rules),
  `black`, and `mypy --strict`-adjacent checks across the entire `src/` and
  `tests/` tree. Fixed everything that came back: ~30 unused imports, several
  dead local variables (`page = self._engine.page` assigned but never used —
  3 occurrences; `delay = await random_delay(...)` — the call's side effect
  was needed, the return value wasn't), an f-string with no placeholders, a
  malformed `# type: ignore` comment, missing type annotations on two
  collections, and a `None`-safety gap in the Gemini provider.
- **mypy now passes cleanly** on all 34 source files. **Ruff passes cleanly.**
  **Black formatting is consistent.** **All 57 tests pass** (was 0 runnable
  before this review, due to the collection error).
- Split `requirements.txt` (runtime) from `requirements-dev.txt` (test/lint/
  type-check tooling), and added upper version bounds so a future major-version
  bump in a dependency doesn't silently change behavior.

## New scaffolding added

- `pyproject.toml` — single source of truth for black/ruff/mypy/pytest config.
- `.github/workflows/ci.yml` — lint + format-check + type-check + test on
  every push/PR, against Python 3.11 and 3.12.
- `.pre-commit-config.yaml` — ruff + black + basic hygiene hooks
  (large-file check, merge-conflict markers, private-key detection) on commit.
- `Dockerfile` / `.dockerignore` — reproducible containerized runs, with
  Playwright/Chromium system deps installed and credentials/data explicitly
  *not* baked into the image.
- `SECURITY.md` — credential handling + the ToS/account-risk disclosure above.

## What I deliberately did *not* do

- **Did not rewrite the ORM models to SQLAlchemy 2.0's `Mapped[]` declarative
  style.** The current `Column()`-based models work correctly (all DB tests
  pass) and mypy now passes against them; migrating styles is a worthwhile
  future improvement but a larger, riskier change than the scope here
  justified given everything already works.
- **Did not expand or "improve" the bot-detection evasion in `stealth.py`.**
  I cleaned up its formatting/imports like everything else, but deliberately
  did not add new evasion techniques — see `SECURITY.md` for why.
- **Did not increase test coverage beyond what was needed to fix the broken
  suite.** Coverage is currently concentrated in `ai/`, `database/`, and
  `utils/` (the parts with the clearest pure-function/repository boundaries).
  `browser/`, `orchestrator/`, and `main.py` have 0% coverage — they're
  Playwright-driven and would need either a headless integration-test
  harness or much heavier mocking to test meaningfully. That's a legitimate
  next investment if you want CI to catch regressions in the apply/search
  flow itself, but it's a project of its own, not a quick fix.
