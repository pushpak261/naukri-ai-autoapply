# Implementation Plan: Final Polish & Automation

This plan covers the final steps of hardening the agent's browser interactions, setting up your local environment for a dry run, and preparing the GitHub Actions cron job.

## Proposed Changes

### 1. Code Cleanup
#### [MODIFY] [agent.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/orchestrator/agent.py)
- Remove the remaining `await qa.flush_cache()` and `await matcher.flush_cache()` calls that were missed in the previous refactoring step.

### 2. Harden Browser Automation
#### [MODIFY] [interactions.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/browser/interactions.py)
- Import the `tenacity` retry library to add robust exponential backoff.
- Wrap `human_type`, `safe_click`, and `js_click` methods with `@retry` decorators to automatically recover from `TimeoutError` or stale elements without crashing the agent.
- Add specific retry thresholds (e.g., max 3 attempts) so the agent gracefully fails after genuine blockages instead of hanging forever.

### 3. Setup Local Environment (`.env`)
- Copy `.env.example` to `.env` so you have a clean template to enter your Naukri credentials and Gemini API key.

## User Action Required

Once the code changes are made, I will hand it back to you to:
1. Fill in your credentials in the newly created `.env` file.
2. Run the Dry-Run command yourself using:
   ```bash
   python -m src.main run --dry-run
   ```
3. Follow the instructions I provide to add `GEMINI_API_KEY`, `NAUKRI_EMAIL`, `NAUKRI_PASSWORD`, and `RESUME_KEY` to your GitHub Repository Secrets to activate the Cron Job.

> [!IMPORTANT]
> Since the credentials require your private API keys and passwords, I cannot perform the live dry run myself. I will set up the environment and wait for you to run the command!

**Do you approve of this plan?**
