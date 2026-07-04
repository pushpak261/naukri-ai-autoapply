# Modular Job Filter Class Refactoring Plan

## Goal
Decouple job filtering and sorting logic from the core web scraping scripts, moving it into a dedicated, modular `JobFilter` class. This improves code organization and makes the filtering criteria easily testable and extensible.

## Problem Context
Job validation (e.g., matching target keywords, checking company names against a blacklist, discarding purely remote jobs if local is preferred) was originally hardcoded directly into the browser DOM interaction scripts (`search.py` / `helpers.py`).
- This made testing filters impossible without a live browser instance.
- Adding new filtering conditions caused the scraping loop to grow excessively long and complex.

## Proposed Changes

---

### Centralize Filtering Logic

#### [NEW] [utils/filters.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/utils/filters.py)
- Create a new `JobFilter` OOP class.
- Implement methods for discrete filtering operations:
  - `is_valid_title(title: str)`: Matches job titles against the configured inclusion/exclusion keywords.
  - `is_valid_company(company: str)`: Checks if the company is in the configured exclusion blocklist.
  - `is_scam_or_consultancy(description: str)`: Runs heuristic regexes to flag suspicious job descriptions.
- The `JobFilter` class will be instantiated with the `SearchSettings` and `ExclusionSettings` dependencies.

#### [MODIFY] [browser/search.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/browser/search.py)
- Remove all raw string manipulation and filtering regexes from the scraping loop.
- Instantiate `JobFilter` at the start of the search cycle.
- Simply call `if not filter.is_valid_job(job_data): continue` to cleanly discard unwanted listings before sending them to the LLM or Database.

---

## Verification Plan

### Automated Tests
- Create unit tests for `JobFilter` in `tests/` that pass mocked job titles and company names to verify accurate inclusion/exclusion logic without needing Playwright or a live browser.

### Manual Verification
- Run a live job search and verify the terminal logs explicitly indicate when jobs are skipped due to title mismatch, company exclusion, or scam heuristics, matching previous behavior.
