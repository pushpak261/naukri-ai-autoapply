# Refined URL Generation and Pagination Algorithm

We discovered the root cause of the pagination bug:
1. **Adding `k` and `l` to query parameters causes Naukri's router to break or drop filters on subsequent pages.**
2. When the URL contains `-2` (or any other page suffix) and also has `k` and `l` query parameters, the server either drops other filters or redirects back to page 1.
3. If we do NOT pass `k` and `l` as query parameters, Naukri's routing engine parses the slug path natively (e.g., `full-stack-developer-jobs-in-bangalore-2` or `c-plus-plus-developer-jobs-in-bangalore-2`), and correctly applies the active filters (`experience`, `jobAge`, `salary`) across all paginated pages!

## Proposed Changes

---

### Utility Abstractions

#### [MODIFY] [helpers.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/utils/helpers.py)

- Modify `NaukriURLUtility.build_search_url` to:
  1. Translate technical special characters and patterns into accurate slug words (e.g., `C++` -> `c-plus-plus`, `C#` -> `c-sharp`, `.NET` -> `dot-net`).
  2. Append page suffix directly to URL path slug for pages > 1 (e.g., `full-stack-developer-jobs-in-bangalore-2`).
  3. **Omit `k` and `l` query parameters completely** (to prevent the routing engine from dropping filters or redirecting on paginated pages).

---

### Search Orchestration

#### [MODIFY] [search.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/browser/search.py)

- Retain redirect detection:
  - If a page redirects back (e.g. expected `-2` but loaded URL does not contain `-2` because there are not enough jobs to fill a second page), gracefully break the loop and stop pagination.

---

### Test Suites

#### [MODIFY] [test_helpers.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/tests/test_helpers.py)

- Update tests to ensure `k` and `l` are omitted from search URLs and only slug generation/pagination path suffixes are asserted.

---

## Verification Plan

### Automated Tests
- Run `pytest tests/test_helpers.py` to verify helper methods.
- Run `pytest` on the entire workspace.
