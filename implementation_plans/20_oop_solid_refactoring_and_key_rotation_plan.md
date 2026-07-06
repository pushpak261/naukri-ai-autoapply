# OOP & SOLID Refactoring and Gemini Key Rotation Plan

## Goal
Restructure the entire monolithic codebase into an Object-Oriented (OOP) and SOLID-compliant architecture, improving maintainability, testability, and separation of concerns. Additionally, introduce API key rotation for the Gemini Provider to handle quota exhaustion gracefully.

## Problem Context
As features were iteratively added, files like `helpers.py`, `login.py`, and `gmail_otp.py` grew into large procedural scripts with tightly coupled logic. 
- Responsibilities like database management, browser automation, and AI prompt engineering were intertwined.
- The Gemini API frequently hits rate limits (429/503), but the system relied on a single hardcoded API key, causing entire job runs to fail prematurely.

## Proposed Changes

---

### Core Architecture Overhaul (SOLID Principles)

#### [MODIFY] [browser/engine.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/browser/engine.py)
- Refactor the browser initialization into a dedicated `BrowserEngine` class to encapsulate Playwright setup and teardown.

#### [MODIFY] [browser/login.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/browser/login.py)
- Convert procedural login steps into a cohesive `LoginHandler` class. 
- Isolate the state (page object, credentials) into class instance variables rather than passing them continuously.

#### [MODIFY] [utils/gmail_otp.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/utils/gmail_otp.py)
- Refactor the Gmail API IMAP logic into a `GmailOTPFetcher` class (Single Responsibility Principle).

#### [MODIFY] [orchestrator/agent.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/orchestrator/agent.py) & [orchestrator/factory.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/orchestrator/factory.py)
- Introduce a Dependency Injection/Factory pattern in `factory.py` to instantiate the AI providers, Database, and Browser, passing them cleanly to the main `Agent` class.
- The `Agent` class will now solely coordinate workflow, delegating actual work to injected services.

---

### Gemini API Key Rotation

#### [MODIFY] [ai/providers/gemini.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/ai/providers/gemini.py)
- Refactor `GeminiProvider` to accept a list of API keys.
- Implement an internal `_rotate_key()` method that cycles through available keys when a `ResourceExhausted` (429) or quota limit error occurs during LLM inference.
- Ensure the state of the active key is maintained across the singleton instance.

---

## Verification Plan

### Automated Tests
- Run `pytest` to ensure all newly decoupled classes (like `test_gmail_otp.py` and `test_backup.py`) continue passing their unit tests under the new OOP structure.

### Manual Verification
- Execute `python -m src.naukri_agent.main run` to verify that the end-to-end flow correctly initializes the factory, boots the browser, and completes job applications without regression.
