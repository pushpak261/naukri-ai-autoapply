# Login via OTP Flow Implementation Plan

This plan details the design and changes required to implement direct login via Mobile Number + Gmail OTP instead of using the Email + Password flow, while fully preserving the original password login as a fallback.

## Proposed Changes

### Configuration Layer

#### [MODIFY] [settings.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/config/settings.py)
* Add `mobile_number` string setting under the `NaukriCredentials` model class (defaulting to empty string).
* Update `_apply_env_overrides` mapping to support `NAUKRI_MOBILE_NUMBER` environment variable.

---

### Selectors Layer

#### [MODIFY] [constants.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/config/constants.py)
* Add the following selectors to `LoginSelectors`:
  * `USE_OTP_LOGIN_LINK` = `'//button[contains(text(), "Use OTP to Login")] | //*[contains(text(), "Use OTP to Login")]'`
  * `MOBILE_INPUT` = `'input[placeholder*="mobile number" i], input[placeholder*="Mobile Number" i], input[id="mobile-input"]'`
  * `GET_OTP_BUTTON` = `'//button[contains(text(), "Get OTP")]'`
* Update `OTP_SUBMIT` to support "Login" button text in addition to "Submit" or "Verify":
  * `OTP_SUBMIT` = `'//button[contains(text(), "Submit") or contains(text(), "Verify") or text()="Login"]'`

---

### Browser/Login Layer

#### [MODIFY] [login.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/login.py)
Update the login execution path inside `_perform_login()`:
* Check if `self._settings.naukri.mobile_number` is configured, alongside Gmail OTP credentials.
* **Flow A (Password Login - Fallback):** If `mobile_number` is not set, proceed with the original Email + Password + optional OTP verification.
* **Flow B (OTP Login - New default):** If `mobile_number` is set:
  1. Navigate to the Naukri login page.
  2. Click the `USE_OTP_LOGIN_LINK` to switch the form to Mobile Login.
  3. Enter the configured `mobile_number` into `MOBILE_INPUT`.
  4. Click `GET_OTP_BUTTON` to trigger the OTP email from Naukri.
  5. Call `_handle_otp()` which will poll Gmail, extract the OTP, input it, and submit the form to verify.

---

## Verification Plan

### Automated Tests
* Run `pytest` to ensure existing credentials parsing, caching, and matching unit tests continue passing.

### Manual Verification
* Run the agent locally:
  ```bash
  python -m src.main run
  ```
* Ensure it navigates to Naukri, switches to OTP mode, inputs the mobile number, triggers the OTP, fetches it from Gmail, and logs in successfully.
