# Add Profile Refresh Scheduled Task

This plan outlines the implementation details for automating a daily profile refresh on Naukri at 7:00 AM IST. Refreshing the profile (by saving the resume headline without making changes) helps keep the Naukri profile marked as "Active/Recently Updated" to recruiters, boosting search visibility.

## Proposed Changes

### Configuration
#### [MODIFY] [constants.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/config/constants.py)
Add `ProfileSelectors` class to store XPath selectors for the profile page.
- `PROFILE_PAGE_URL = "https://www.naukri.com/mnjuser/profile"`
- `RESUME_HEADLINE_EDIT_ICON`: Selects the pencil icon next to the "Resume headline" section.
- `SAVE_BUTTON`: Selects the "Save" button in the modal.

---

### Browser Automation Layer
#### [NEW] [profile.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/profile.py)
Create a new `ProfileRefresher` class.
- Methods: `refresh()`
- Logic:
  1. Navigate to the profile page URL directly.
  2. Wait for the page to load and find the "Resume headline" edit icon.
  3. Click the edit icon to open the modal.
  4. Wait for the modal to be visible.
  5. Click the "Save" button.
  6. Wait for the modal to close or a success indicator.
  7. Log success/failure gracefully.
  8. Rely heavily on existing `IBrowserInteractions` for resilient clicks and waits.

---

### Dependency Injection & Orchestrator
#### [MODIFY] [factory.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/orchestrator/factory.py)
- Add `create_profile_refresher(self) -> ProfileRefresher` method to inject dependencies (`engine`, `interactions`, `settings`) into the `ProfileRefresher`.

#### [MODIFY] [agent.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/orchestrator/agent.py)
- Add `async def refresh_profile(self)` to `NaukriAgent`.
- Logic:
  1. Initialize logging.
  2. Launch browser via `self._engine.launch()`.
  3. Perform login via `LoginHandler`.
  4. Instantiate and run `ProfileRefresher`.
  5. Clean up by closing the browser (`self._cleanup()`).

---

### CLI Entry Point
#### [MODIFY] [main.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/main.py)
- Add a new click command: `@cli.command("refresh-profile")`
- Add `async def _refresh_profile()` to set up the DB, factory, and agent, then call `await agent.refresh_profile()`.

---

### GitHub Actions (Scheduler)
#### [NEW] [profile-refresh.yml](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/.github/workflows/profile-refresh.yml)
- Create a new GitHub Action workflow copying the boilerplate from `auto-apply.yml`.
- Schedule: `cron: '30 1 * * *'` (01:30 UTC = 7:00 AM IST daily).
- Step modification: Instead of `run`, the execution step will call `xvfb-run python -m src.main refresh-profile`.

## Verification Plan

### Manual Verification
- We can run `python -m src.main refresh-profile` locally to observe the browser (or run it headless) navigating, clicking edit, and saving the headline.
- The `profile-refresh.yml` file will be pushed to GitHub to verify it triggers correctly on schedule.
