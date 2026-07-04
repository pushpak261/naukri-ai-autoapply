# LLM Transient Error Retry Mechanism & Quota Bypass Plan

## Goal
Implement a robust retry mechanism with exponential backoff for all LLM API calls to mitigate transient network errors, HTTP 503 Service Unavailable errors, and temporary quota limits, ensuring that the background agent doesn't crash unnecessarily during long-running batch job analysis operations.

## Problem Context
The agent relies on Google's Gemini API to analyze job descriptions and determine fit based on the user's resume. 
- Google's free tier has strict rate limits (RPM/RPD) and occasionally returns transient 503 errors when the API is under heavy load.
- If the agent encounters a single error, it currently throws an exception and halts the entire scraping process.
- We need the agent to patiently wait and retry before giving up on a job or falling back to a different model.

## Proposed Changes

---

### Retry Logic Implementation

#### [NEW] [tests/test_retry.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/tests/test_retry.py)
- Implement unit tests for the retry mechanism to ensure it respects the maximum number of attempts and calculates backoff delays correctly before integration.

#### [MODIFY] [utils/helpers.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/utils/helpers.py) (or `decorators.py`)
- Introduce a generic `@with_retry(max_attempts=3, backoff_factor=2.0)` decorator.
- The decorator will catch `google.api_core.exceptions.ResourceExhausted` and `google.api_core.exceptions.ServiceUnavailable`.
- Upon catching these specific transient exceptions, the thread will `time.sleep()` before re-invoking the wrapped function.
- If `max_attempts` are exceeded, it raises a custom `LLMAPIError` for the orchestrator to catch (which will then trigger a model fallback).

#### [MODIFY] [ai/providers/gemini.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/ai/providers/gemini.py)
- Wrap the core `_call_gemini_api()` text generation inference method with the `@with_retry` decorator.

---

## Verification Plan

### Automated Tests
- Run `pytest tests/test_retry.py` to assert the backoff multiplier correctly spaces out execution time and ultimately fails exactly after the configured limit.

### Manual Verification
- Execute a deep search on Naukri that parses >100 jobs to intentionally hit rate limits. 
- Observe the console logs to ensure `[WARNING] Transient API Error... Retrying in X seconds` appears and that execution resumes successfully on subsequent attempts.
