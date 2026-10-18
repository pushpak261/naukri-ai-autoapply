# ApplyOS logic audit — 17 October 2026

This audit fixes defects found in the local Python API and React dashboard. Passing automated tests establishes the checked behavior; it does not guarantee that every external platform workflow will succeed.

## Application-flow audit - 18 October 2026

Fixed repeated submission paths: LinkedIn submits once and polls for confirmation without forcing submit to escape a form loop; Naukri no longer issues another submit after a previous attempt just because confirmation is delayed. LinkedIn honors existing filled answers, checked radio/checkbox groups and selected choices while treating disabled/select placeholders as unanswered. Extraction no longer duplicates option labels from an already handled form group. Required-field metadata uses the actual is_required flag, so optional unanswered fields can remain empty.

Resume uploads use the selected workspace-confined file and exact input ID. Missing/failed required uploads stop submission, and a resume is not sent to a cover-letter or unrelated attachment field. Ambiguous multi-file inputs are not guessed. Review diagnostics cannot leave review_state undefined after a browser error. Naukri's unsupported external employer path now reports manual handling instead of attempting a native form workflow or claiming success from a generic thank-you page. Preferences states the supported native/Easy Apply scope.

Verification: **1,110 full-suite tests passed**, one Windows symlink test skipped, followed by **8 form-audit tests passed** including a real local Chromium DOM extraction check for prefilled values, radio/checkbox groups and dropdown placeholders. Changed-code lint and compilation passed. No live job-platform applications were sent. Account-specific live acceptance remains required.

## Auto-apply reliability follow-up - 18 October 2026

LinkedIn orchestration now preserves an AI veto even at a high match score, and Gemini failure no longer silently disables matching for later jobs. Screening AI follows use_gemini independently of the matching toggle. Browser and disabled-AI answer fallbacks now use explicit evidence rather than invented personal details, positive consent, salary, tenure or a default city. Skill-specific tenure cannot fall back to total experience; unspecified languages are not inferred. Missing required answers or failed fills block submission. Unmatched choice fields and location suggestions are not filled with their first option, and generic force-fill no longer populates unidentified required fields.

Modal disappearance, missing buttons and generic Done-only dialogs no longer establish success. Confirmed platform text is required. Interrupted/unconfirmed submissions stay uncertain, stop the run for review and are not retried automatically. LinkedIn writes a durable applying claim before browser submission and updates that same application record afterward; applying and uncertain states block duplicates across restart. Naukri recovers interrupted claims to uncertain instead of failed. Its dedup cache now excludes dry-run and skipped outcomes so a validated dry run can be followed by a real application.

Validation includes full isolated regression coverage and focused mocked form/database tests for truthful unknown answers, matching-independent AI screening, confirmed submission, missing required fields, unmatched choices, persistent claims and dry-run-to-live transition. No job-platform submissions were sent during verification. Live Naukri/LinkedIn acceptance, account verification and external employer forms remain separate checks.

Results: full isolated run **1,100 passed, one Windows symlink test skipped**, followed by **335 affected regressions passed** after the final dedup and choice-selector refinements. Changed-code lint and Python compilation passed. Tests intentionally replace older assumptions that defaulted skill tenure to total experience, expanded locations to a hardcoded region, or accepted arbitrary text as a Yes/No selection. No frontend code changed in this follow-up.

## Career Studio - 18 October 2026

Added private saved application packs, role-specific interview rehearsals with answer feedback, and seven-day search plans. Available in Opportunity Copilot and job details. Every generated section must include exact source quotes checked against bounded, allowlisted resume or job context. Unsupported quotes, invalid structured output, missing real records and incomplete seven-day/interview plans fail explicitly. Generated drafts do not submit applications, send messages or modify resumes. Quote presence does not certify every generated claim; review remains required.

Artifacts use UUID paths inside the signed-in workspace, atomic file replacement, private metadata/history and Markdown export. Interview feedback uses the selected saved question and original profile context. Raw resume/contact fields and credentials are excluded from prompts. Answers are sent on request for feedback and are not persisted in artifacts. Cancellation guards prevent stale results after navigation; account cache keys separate users.

Verification: full isolated suite **1,087 passed, one Windows symlink test skipped**, 12 existing warnings. Frontend **18 tests passed**, TypeScript and production build passed, backend lint passed; two existing frontend Fast Refresh warnings remain. A live Gemini structured-output check used fictional evidence only and passed source-quote validation. Browser verification confirmed real-data empty states, disabled role-specific actions without listings, saved-work controls and Career Studio rendering in the signed-in app. No personal resume was sent for verification and no platform application was submitted. Local health returns HTTP 200.

## Real-data-only client build - 18 October 2026

Removed fictional demo source, sample datasets, navigation links and client demo documentation. The former demo URL redirects to the real authenticated workspace. Removed the explicitly marked disposable QA account from active storage, retaining a reversible archive under artifacts (excluded from exports). Personal accounts and saved records are preserved. New client accounts start without sample search preferences. Dashboards refresh stale queries on focus; no data is invented when records are missing. Market views show N/A for unavailable salary figures, label submission rates accurately, exclude unscored applications from score brackets and skip ambiguous/non-LPA salaries rather than relabelling them as INR lakhs/year. Overview job totals now count saved listings rather than summing only ten recent run logs. Automated fixtures remain in tests and never populate client workspaces.

Verification: 36 focused dashboard/export tests passed, followed by all 3 real-data-only regressions (including saved-listing totals and source isolation); 18 frontend tests passed. TypeScript and production build passed. Backend lint passed; frontend lint retains two existing Fast Refresh warnings. The built assets contain no demo chunk, and the client ZIP excludes demo datasets, runtime records and retired QA archives. Updated local health endpoint returns HTTP 200.

## Application-wide Gemini integration - 18 October 2026

Added authenticated, workspace-scoped structured Gemini advice for resume improvement, skills planning, job comparisons, application strategy, career planning, agent preferences, market sample interpretation, listing risk review and analytics. Dashboard controls show loading, retryable errors, actual model and sample counts. Navigation cancels stale UI requests. Explicit field allowlists omit contact details, raw resume text, credentials and session files from advisor prompts. Outputs are schema validated, timeout bounded and rendered as text. Advice makes no automatic changes or submissions. Short-lived provider clients close their HTTP connections.

Fixed matching cache identities to include profile content, listing details, AI mode, matching toggle, model and score threshold. Existing outdated assessments are bypassed. LinkedIn prompts no longer demand always-true recommendations; invalid model output cannot silently become a local apply recommendation. Both platform matching paths validate response types and score ranges and preserve an AI veto.

Verification: full isolated suite **1,076 passed, one Windows symlink test skipped**; final cleanup-focused set **34 passed**. Frontend **18 tests passed**, TypeScript/production build passed; lint has two existing Fast Refresh warnings. Live Gemini with the saved key returned schema-valid structured advice for fictional candidate data; no personal resume was sent in that check. Browser confirmed the advisor controls render. Automatic approval review blocked a live advisor browser click because it could transmit personal data, so that payload was not used for verification. Live platform submissions remain untested.

## Changes

- Closed SQLite backup connections before retention cleanup, fixing Windows file locks.
- Added the timezone database required for scheduled runs on Windows and normalized schedule times before comparing them.
- Derived default storage paths from the selected workspace for both agents while preserving explicit path overrides.
- Made health checks report HTTP 503 when database or disk checks fail.
- Fixed a LinkedIn title-filter constructor mismatch that could stop a run before processing jobs. Added a mocked full-run regression.
- Corrected overlapping skill-strength buckets and rejected malformed skill entries gracefully.
- Prevented delayed authentication responses from restoring a signed-out account or retrying a previous account's request with a new account's token.
- Preserved sessions through temporary connection/renewal outages and formatted API validation messages for users.
- Scoped locally saved resume history to the signed-in email. Unattributable legacy shared history is intentionally ignored.
- Keyed job, application, inspector, log, and match-cache reads by their inputs so older responses cannot replace newer selections.
- Added visible load failures/retry paths and handled rejected asynchronous loads. Cache-clear failures release the busy state.
- Invalidated dashboard queries after restore, import, clear-data, and preference changes.
- Included frontend regression tests and newly authored backend source/tests in source handovers.

## Verification

- Full backend suite in an isolated source copy with clean configuration: **1,034 passed, 1 skipped**, 12 warnings. The skip is the Windows symlink-creation restriction. Most warnings concern intentionally short JWT keys in existing tests.
- Focused backend workflow checks: **45 passed**, before adding the additional skill-analysis regression included in the full run.
- Frontend API/session/history regressions: **16 passed**.
- Frontend TypeScript check and production build: passed.
- Frontend lint: no errors; two existing Fast Refresh export warnings.
- Browser smoke checks use a disposable local account. Login, overview, jobs, and simulated jobs failure/retry were verified without submitting real applications.
- Full backend tests cover authenticated feature endpoints, two-user storage boundaries, queue semantics, schedules, resume upload/edit, backup restore, export/import, webhook dispatch, and agent helpers.

Test evidence is retained locally under `artifacts/logic-audit/`; runtime copies and logs are excluded from the client source package.

## Remaining acceptance work

Use the client's own credentials to validate Naukri and LinkedIn sign-in, CAPTCHA/verification challenges, current job forms, dry runs, and a small explicitly approved live application. Paid AI behavior, API quotas, email/webhook destinations, deployment persistence, and cloud resource limits need testing in the client's environment. No live applications were submitted during this audit.

The repository still has informational Python lint/type-check debt. The broad mypy review initially reported 37 diagnostics, including missing library stubs and optional browser-controller annotations; the concrete LinkedIn constructor defect was fixed. Python static checks are not represented as passing. Docker/Koyeb and PostgreSQL integration were not exercised locally. Complete the acceptance checklist in `CLIENT_HANDOVER.md` before representing the project as production accepted.

## Command Center follow-up

The `/agent-control` review additionally corrected:

- Start/stop operations now share lifecycle locks. A failed termination retains the process reference and returns an error instead of claiming it stopped.
- Parallel status, stop, and log endpoints recognize agents started in single mode. Failed parallel launches return per-platform outcomes without hiding a platform that already started.
- Output readers schedule delivery on the asyncio event loop and ignore messages from replaced processes. SSE frames encode multiline output correctly; zero history requests do not replay the whole buffer. Log query sizes are bounded and stopped-run output is preserved.
- The frontend uses one cancellable monitor for the selected view, serializes polling, ignores obsolete responses, and refreshes after in-flight polling settles. Stream history is no longer fetched concurrently with a separate snapshot, preventing duplicate replay. Stream errors fall back to polling and connection labels reflect the actual stream state.
- Platform switches close the old stream and cancel its pending render batch. Log storage is bounded by both lines and characters, including enormous single lines. Incoming stream messages are batched for rendering.
- Start/restart buttons cannot double-submit. Partial/failed starts show platform errors; unknown status disables start/restart while retaining Stop. Uptime uses the server start time rather than counting from zero when the page opens.

Follow-up verification: **41 backend tests passed** (lifecycle regressions, dashboard workflows and user isolation); **18 frontend tests passed**; production build and TypeScript passed. Ruff passed on the changed backend lifecycle files and their regression suite. Frontend lint retains the two existing Fast Refresh warnings.

Browser-only mocked lifecycle checks verified total/partial start failures, initialized uptime, stale stream rejection on a log-platform switch, fallback after stream failure, safe controls during a status outage, and stop confirmation with retained logs. All test overrides were removed afterward. No real job agents or submissions were launched by these checks.

## Opportunity Copilot and local recovery — 18 October 2026

- Added `/copilot`: a private shortlist of up to 500 recent saved jobs with explainable structured-skill coverage, profile readiness, location and stated-experience cautions, daily next steps and recurring skill gaps. Existing submissions are marked in progress instead of recommended for duplicate applications.
- Added role preparation briefs with profile-grounded prompts, recruiter questions, review checklists and editable outreach drafts. These use local evidence rules without paid API calls; scores are not hiring probabilities. Drafts contain explicit placeholders rather than invented personal achievements. Copilot does not queue jobs or send messages.
- Both agents use a bounded skill-evidence priority boost to process better-supported candidates earlier. The original eligibility score is stored separately; filters, AI assessments and daily limits are preserved.
- Tested missing/malformed evidence, aliases without substring false matches, real queue ordering, unchanged eligibility scores and cross-account privacy. Responsive evaluation passed at 1440, 768 and 375 pixels using fictional jobs in an isolated preview.
- Diagnosed a disconnected local dashboard with no backend listener and an obsolete cached frontend. Restored the backend as a hidden background process, added repeated health checks so the banner clears on recovery, disabled offline PWA registration for local builds, and added a one-time migration for old local service workers. Local HTML responses are no-store.

Final verification: **1,053 backend tests passed, 1 Windows symlink test skipped**; **18 frontend regression tests passed**; TypeScript and production build passed. The local delivery regression also passed separately after the final HTML cache-header refinement. Browser simulation confirmed the outage banner appears and clears automatically, with no active service worker afterward. Existing two frontend Fast Refresh warnings remain.

## AI parsing and shared configuration follow-up

The local account configurations had Gemini disabled and no API key. That explains the visible “Parsed locally without AI” result. No developer or other account's key was borrowed.

- Added a password-style Gemini key input, saved-key connection test and shared AI preferences for both agents. The connection test sends a small diagnostic prompt, not a resume. `/api/ai/status` exposes configuration flags without returning the key.
- Resume uploads from the UI now request AI explicitly. Reparse with AI upgrades the existing uploaded file, bypasses local cached profiles, validates structured output, records model provenance, and preserves the old profile on failure. Resume calls have bounded longer timeouts. LinkedIn AI parsing reuses the validated parser rather than unchecked local caches.
- Updated default Gemini model selection to `gemini-2.5-flash` and retained a bounded fallback list. LinkedIn now passes response schemas to the SDK. Google's model documentation confirms structured-output support: https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash
- Removed candidate-specific matching instructions and mandatory-positive screening instructions. Matching respects an AI veto as well as score thresholds. Total experience is no longer forced to one year or reused automatically as skill-specific tenure. Unsupported personal details and missing answers require review. New profile-context answer caches do not reuse legacy guessed answers.
- Analytics and Copilot evidence coverage remain database/rule-based. They are not relabeled as AI output.

Verification: **1,060 backend tests passed, one Windows symlink test skipped**. The final focused screening and AI-readiness set passed **166 tests**, including the last skill-specific-tenure guard. Frontend regressions passed **18 tests**, production build and TypeScript passed. Mock-provider tests verify schema handling, local-cache bypass, upgrade of existing profiles, shared settings, preservation on failure, and missing-key errors. Browser checks verified the key/test controls and AI reparse action. Live Gemini output remains unverified until the account owner saves a valid key with available quota.
