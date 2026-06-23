# Fix: Naukri Login Fails in GitHub Actions CI but Works Locally

## Root Cause Analysis

After a deep trace of the entire flow, here is exactly what's happening and why:

### The Problem Chain

When running in GitHub Actions:
1. The browser launches **headless** (`headless=True` because `CI=true`)
2. It navigates to `https://www.naukri.com/nlogin/login`
3. **Naukri's Cloudflare/bot protection detects the headless browser** and serves either:
   - An "Access Denied" page
   - A CAPTCHA challenge page  
   - A completely different DOM layout (no login form rendered)
4. The selectors (`input[placeholder="Enter Email ID / Username"]`) can't find anything because **the login form was never rendered**
5. The `wait_for_selector` times out after 30 seconds → `TimeoutError`

### Why It Works Locally

On your laptop, the browser launches **headed** (`headless=False`). Headed Chromium passes most bot detection checks because:
- The window manager is real (not `xvfb`)
- `navigator.webdriver` behaves differently in headed mode
- The GPU/rendering pipeline is real
- Screen dimensions, WebGL, and canvas fingerprints are authentic

### Evidence

1. When I ran Playwright headless earlier against `naukri.com/nlogin/login`, the page title returned was **"Access Denied"** — confirming Cloudflare is blocking it
2. The `document.querySelectorAll('input')` returned **zero elements** — the login form was never served
3. Your stealth scripts in [stealth.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/stealth.py) patch `navigator.webdriver`, plugins, etc., but these are **not sufficient** against modern Cloudflare detection which also checks:
   - `HeadlessChrome` in the user-agent string (Playwright adds this automatically in headless mode)
   - Missing GPU compositor info
   - `xvfb` virtual display fingerprint  
   - Chrome DevTools Protocol detection

### The Two Critical Bugs

#### Bug 1: Session Decryption Key Mismatch
In [engine.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/engine.py#L60-L67), the `_get_fernet()` method derives the encryption key from `NAUKRI_PASSWORD`:
```python
secret = self._settings.naukri.password or "default_secret_fallback_123"
key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
```

But in [sync_session.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/sync_session.py) and the [workflow](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/.github/workflows/auto-apply.yml#L39-L53), the session is encrypted/decrypted using `RESUME_KEY` (a Fernet key). These are **two completely different keys**!

So the session restoration always fails in CI:
```
WARNING  Failed to restore encrypted session state:
INFO     Loaded unencrypted session. It will be encrypted on next save.
```
The workflow decrypts `session.enc` → `naukri_session.json` using `RESUME_KEY`, but then `engine.py` tries to decrypt it again using `NAUKRI_PASSWORD`-derived key and fails. The fallback reads it as unencrypted JSON, which actually works — but **the session cookies themselves have expired** by the time the cron runs, so session restoration fails anyway.

#### Bug 2: Headless Detection Blocking
Even after session failure, the bot falls through to fresh login. But in headless mode, Naukri's bot protection blocks the login page entirely, so the email input field never appears.

> [!IMPORTANT]
> **The fundamental issue is that GitHub Actions headless Chromium gets blocked by Naukri's anti-bot protection.** No amount of selector fixes will help because the login form is never rendered.

## Proposed Changes

### Strategy

The only reliable approach is to **never need to log in from CI**. Instead:
1. Make session restoration bulletproof (fix the key mismatch)
2. Ensure you sync a fresh session from your laptop before it expires
3. Add a diagnostic screenshot on login failure for future debugging
4. Improve the stealth configuration as a secondary defense

---

### Component 1: Fix Session Key Mismatch

#### [MODIFY] [engine.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/engine.py)

The `_get_fernet()` method currently derives a key from `NAUKRI_PASSWORD`. This is incompatible with `sync_session.py` and the CI workflow, which both use `RESUME_KEY`. We need to unify on one approach.

**Change**: Make `_get_fernet()` use `RESUME_KEY` env var first (matching the CI workflow), falling back to the password-derived key for backward compatibility.

#### [MODIFY] [auto-apply.yml](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/.github/workflows/auto-apply.yml)

Pass `RESUME_KEY` as an env var to the Run step so the engine can use it for session decryption.

---

### Component 2: Harden Headless Stealth for CI

#### [MODIFY] [engine.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/engine.py)

- Use a proper viewport (not `no_viewport: True`) in CI — `xvfb` doesn't have a real display manager, so `no_viewport` causes issues
- Add `--disable-gpu`, `--window-size=1920,1080`, and other CI-specific launch args
- Update user-agent to a current Chrome version for Linux (CI runs Ubuntu, but user-agent says `Windows NT`)

#### [MODIFY] [stealth.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/stealth.py)

- Override `navigator.platform` conditionally for Linux environment  
- Add `navigator.connection` spoofing (modern detection checks this)

#### [MODIFY] [constants.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/config/constants.py)

- Add a Linux-compatible user-agent string constant for CI use

---

### Component 3: Add Diagnostic Screenshot on Login Failure

#### [MODIFY] [login.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/login.py)

- Before returning `False` from `_perform_login`, take a screenshot and log the current URL and page title
- This will capture exactly what Naukri serves in CI (Access Denied, CAPTCHA, etc.)
- Upload the screenshot as a GitHub Actions artifact for debugging

#### [MODIFY] [auto-apply.yml](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/.github/workflows/auto-apply.yml)

- Add a step to upload `data/logs/*.png` as artifacts on failure

---

## Open Questions

> [!IMPORTANT]
> **Session Sync Strategy**: The Naukri session cookies typically expire after ~24 hours. With the cron running 5 times daily, we need a reliable way to keep the session fresh. Currently `sync_session.py` requires manual laptop login. Are you okay with running `python sync_session.py` once daily from your laptop, or would you prefer an automated session refresh approach?

> [!IMPORTANT]
> **RESUME_KEY storage**: I see `resume_key.txt` is in the repo root (and presumably in `.gitignore`). Is `RESUME_KEY` stored as a GitHub Actions secret? I need to confirm this before I modify the workflow to pass it to the run step.

## Verification Plan

### Automated Tests
```bash
python -m src.main run --dry-run
```

### Manual Verification
1. Run the bot locally to confirm login still works
2. Run `python sync_session.py` to create a fresh `session.enc`
3. Push and trigger the GitHub Action manually via `workflow_dispatch`
4. Check the uploaded screenshot artifact if login fails — it should show the actual page content
5. If session is fresh enough, the bot should restore the session and skip login entirely
