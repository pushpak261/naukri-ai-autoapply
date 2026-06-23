# Implementation Plan - Refactor Login Handler to Login Strategy Pattern (OCP)

This plan outlines the refactoring steps to align the login authentication subsystem with the **Open/Closed Principle (OCP)** of SOLID by replacing hardcoded conditional checks with a Strategy Pattern.

---

## User Review Required

> [!IMPORTANT]
> The login module currently branches via conditional settings check (`use_otp_login`). Moving to a Strategy Pattern decouples the login procedure from the handler. This is open to extension, meaning you can add third-party OAuth, SMS, or captcha solver strategies in the future without editing the main login controller.
>
> Please review the detailed analysis in [solid_audit_report.md](file:///C:/Users/pushp/.gemini/antigravity-ide/brain/7ab5f5ea-565a-408e-b692-ef82ce1b5a9b/solid_audit_report.md) before approving.

---

## Proposed Changes

### 1. Define Login Strategy Interface
Add `ILoginStrategy` to define the interface contract for all login types.

#### [MODIFY] [interfaces.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/core/interfaces.py)
*   Add `ILoginStrategy` Protocol defining `async def authenticate(self, login_page: LoginPage) -> bool`.

---

### 2. Implement Concrete Strategies & Decouple Login Handler
Implement the concrete strategies and clean up the conditional branches in the main handler.

#### [MODIFY] [login.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/browser/login.py)
*   Define `PasswordLoginStrategy(ILoginStrategy)` class.
*   Define `OTPLoginStrategy(ILoginStrategy)` class.
*   Update `LoginHandler` constructor to accept `ILoginStrategy`.
*   Update `LoginHandler._perform_login()` to delegate authentication to the injected strategy.

---

### 3. Update Dependency Injection Container
Instantiate and wire the appropriate strategy in the factory.

#### [MODIFY] [factory.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/orchestrator/factory.py)
*   Import `PasswordLoginStrategy` and `OTPLoginStrategy`.
*   In `create_login_handler()`, determine the correct strategy based on settings, instantiate it, and pass it to the `LoginHandler` constructor.

---

## Verification Plan

### Automated Tests
*   Run unit tests: `python -m pytest`
*   Verify that `tests/test_agent_fallback.py` or browser mocks compile and run correctly under the new constructors.

### Manual Verification
*   Execute `python -m src.naukri_agent.main refresh-profile` to ensure the login flow executes correctly with session validation and authentication.
