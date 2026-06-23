# Code Quality & Refactoring Implementation Plan

Detailed plan to address code quality gaps, implement the missing async retry decorator, fix static typing errors, consolidate inline selectors into constants, and maintain the codebase's existing architectural strengths.

---

## Codebase Strengths to Preserve
During this refactoring, we will strictly preserve the following architectural patterns:
1. **Dependency Inversion**: Abstract interfaces defined in [interfaces.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/core/interfaces.py) and initialized in [factory.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/orchestrator/factory.py) must not be bypassed or tightly coupled.
2. **Resilience Strategy**: Fallback patterns (e.g. DOM climbing, alternative selectors, and automatic browser recovery logic) must be kept intact.
3. **Paced Automation Loops**: High-entropy timing patterns (like Gaussian random delays) must be kept to bypass anti-bot detection.

---

## User Review Required

> [!NOTE]
> All changes are targeted at improving code robustness, standardization, and typing validation. There are no breaking API interface changes or CLI usage modifications.

---

## Open Questions

1. **Async-only Retry vs General-purpose Retry**:
   * *Proposed Approach*: Since all target operations (Playwright calls, Gemini API requests, Database operations) are async (`await`), the retry decorator will be built specifically for async functions (`async def`). 
   * *Question*: Do you want the retry decorator to support synchronous functions as well? (Recommended: Async-only to keep the decorator signature simple and fast).

---

## Proposed Changes

### Component 1: Utilities and Configuration

#### [MODIFY] [constants.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/config/constants.py)
* Add selectors for elements that were previously hardcoded:
  * In `LoginSelectors`: Add `NOT_LOGGED_IN_INDICATORS = 'a#login_Layer, a:has-text("Login")'`.
  * In `ApplyFlowSelectors`: 
    * Add `FORM_FALLBACK = 'form[class*="apply"]'`.
    * Add `CHATBOT_MSG_FALLBACK = '[class*="chatbot-msg"]'`.
    * Add `SCREENING_FALLBACK = '[class*="screening"]'`.
    * Add `GENERIC_SUBMIT = '//button[contains(text(), "Submit")]'`.
    * Add `GENERIC_APPLY = '//button[contains(text(), "Apply")]'`.
    * Add `GENERIC_SUBMIT_TYPE = 'button[type="submit"]'`.
    * Add `SUCCESS_SUBMITTED = '//*[contains(text(), "submitted")]'`.
    * Add `SUCCESS_RECEIVED = '//*[contains(text(), "received your application")]'`.

#### [MODIFY] [helpers.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/utils/helpers.py)
* Implement a robust `async_retry` decorator under the `# Retry decorator` section using exponential backoff.
* Update type hints of `clean_text` and `truncate_text` parameters to support optional values (`str | None`) instead of strict `str` to reflect actual fallback behaviors and satisfy type checker constraints.

---

### Component 2: Browser Logic

#### [MODIFY] [apply.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/apply.py)
* Replace hardcoded inline selector strings with corresponding constants:
  * In `_detect_screening_questions` (line 235-237): replace `'form[class*="apply"]'`, `'[class*="chatbot-msg"]'`, and `'[class*="screening"]'` with their respective `ApplyFlowSelectors` equivalents.
  * In `_submit_application` (line 460-462): replace `'//button[contains(text(), "Submit")]'`, `'//button[contains(text(), "Apply")]'`, and `'button[type="submit"]'` with their respective `ApplyFlowSelectors` equivalents.
  * In `_check_application_success` (line 495-496): replace `'//*[contains(text(), "submitted")]'` and `'//*[contains(text(), "received your application")]'` with their respective `ApplyFlowSelectors` equivalents.

#### [MODIFY] [login.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/login.py)
* Replace `'a#login_Layer, a:has-text("Login")'` in `_is_logged_in` (line 223) with `LoginSelectors.NOT_LOGGED_IN_INDICATORS`.

---

### Component 3: Test Suite

#### [NEW] [test_retry.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/tests/test_retry.py)
* Write a new test file containing:
  * Tests validating that the async retry decorator retries function execution upon target exceptions.
  * Tests validating that exponential backoff multiplies delays correctly.
  * Tests validating that non-targeted exceptions are raised immediately without retry.

---

## Verification Plan

### Automated Tests
* Run full test suite using Pytest to ensure no regressions:
  ```bash
  pytest
  ```
* Run specific test suite for utilities and retry:
  ```bash
  pytest tests/test_helpers.py tests/test_retry.py
  ```

### Manual Verification
* Run a dry run of the application CLI to make sure the orchestrator starts correctly and reads the configs:
  ```bash
  python -m src.main run --dry-run
  ```
