# Fix Gemini Job-Matching Pipeline Bugs

This plan details the implementation steps to resolve two bugs in the Gemini job-matching pipeline of the Naukri Auto-Apply agent.

## User Review Required

> [!IMPORTANT]
> - **Fallback model configuration**: We are adding `fallback_model` and `abort_on_quota` options to the `ai` section of `config.yaml` and `src/config/settings.py`. By default, if `fallback_model` is not set and `abort_on_quota` is `true`, the agent will maintain the current behavior (stopping the run immediately).
> - **No dynamic API keys**: We assume that both primary and fallback models use the same `GEMINI_API_KEY`. If the user has different keys for separate GCP projects, we currently use the same key configured.

## Open Questions

None at this stage, as the requirements are clear and complete.

---

## Proposed Changes

### Configuration Layer

#### [MODIFY] [config.yaml](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/config.yaml)
- Add `fallback_model` (optional, default empty/none) to the `ai` section.
- Add `abort_on_quota` (default `true`) to the `ai` section to control whether the agent halts the entire run when daily quota is exhausted and no fallback model is set/available.

#### [MODIFY] [settings.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/config/settings.py)
- Update the `AISettings` Pydantic model to include fields:
  - `fallback_model: str | None = None`
  - `abort_on_quota: bool = True`

---

### AI & Provider Layer

#### [MODIFY] [gemini.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/ai/providers/gemini.py)
- Add a public `set_model(self, model_name: str) -> None` method to `GeminiProvider` to allow dynamically switching the active model name during a run.

#### [MODIFY] [job_matcher.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/ai/job_matcher.py)
- Raise the token limit passed to `self._llm.generate_content(...)` to use the configured `max_output_tokens` (from settings, which defaults to 4096) instead of the hardcoded `2048`.
- Wrap the `json.loads` statement in a nested try-except block. On encountering `json.JSONDecodeError`, retry the AI call *once* using a stricter prompt that emphasizes the return of complete, valid JSON.
- On persistent JSON parsing failure, log the entire raw response content so that it is fully debuggable without guessing.

---

### Orchestrator Layer

#### [MODIFY] [agent.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/orchestrator/agent.py)
- In the job-processing loop, update the `LLMQuotaExceededError` exception handler to:
  1. Check if `self._settings.ai.fallback_model` is configured.
  2. If a fallback model is available and has not been used yet, switch the provider's active model, update the settings, and retry the match evaluation for the current job.
  3. If no fallback model is available, check `self._settings.ai.abort_on_quota`. If `true`, abort the run (break the loop). If `false`, log a warning and continue to the next job in the queue.

---

## Verification Plan

### Automated Tests
- Run `python -m pytest` to check that the current tests still pass and add new tests for fallback logic and JSON parsing retry fallback.
- Run `python -m pytest tests/test_job_matcher.py` explicitly to verify parsing failures are handled cleanly.

### Manual Verification
- We can run the agent in dry-run mode or simulate a 429 quota exception to verify the fallback switching message and model replacement behavior.
