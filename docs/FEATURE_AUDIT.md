# Dashboard feature audit

Audit performed 2026-10-11 against the Vercel frontend and its Koyeb API.

## Verified

- Live frontend: login renders; 20 dashboard pages render with a UI-only identity fixture and real read-only API responses. This did not establish a real production login.
- Local browser: real dashboard login followed by all 20 pages, waiting for rendered page headings; no uncaught JavaScript errors.
- Isolated backend: 42 dashboard GET routes return successfully using a real dashboard JWT.
- Isolated workflows: account CRUD/activation, export/import with ID remapping and atomic rollback, SQLite backup/restore, clear-data running-agent guard, resume PDF upload/local parsing/profile edits/config persistence, webhook CRUD and targeted test delivery, apply queue and retry semantics, scheduler dispatch and once-per-day scheduling, observed application-status synchronization.
- External browser status observation, process launch and outbound webhook delivery use test doubles in workflow tests. They are not production delivery evidence.
- Backend regression suite: 969 tests pass. Frontend build, lint (four existing warnings), and five API-client tests pass.

## Repairs

Previously anonymous private APIs now require a dashboard JWT or configured operator API key. Vercel forwards /api to Koyeb so refresh cookies can remain first-party. Full exports no longer truncate records. Imports validate data and remap application foreign keys transactionally. SQLite backups use the online backup API, including WAL contents; restoration checks integrity and rebuilds repository caches.

Batch Apply previously inserted successful application records without submitting jobs. It now queues work for the browser pipeline. Retries are restricted to eligible failed attempts. A lifecycle scheduler dispatches pending work and configured scheduled runs. Single/multi start requests share a lock and reject overlapping platform runs. Failed browser/login runs report an error instead of completed. Queued applications are excluded from failure totals.

Resume upload works with local parsing when Gemini is disabled, persists missing resume configuration sections, limits uploads and avoids reusing another PDF's profile. Eligible Naukri jobs use the matcher and configured score threshold instead of receiving a fabricated 100% score. Sync Status verifies observed Naukri application pages and displays asynchronous progress; it no longer invents recruiter responses. Webhook Test targets only the selected webhook and reports delivery errors.

## Remaining coverage and implementation gaps

This audit is not a certification that every feature works in production.

- Real Naukri and LinkedIn login, OTP/CAPTCHA/session recovery, Gemini quota/model responses, actual application submission and recruiter-side status require operator-owned test accounts and deployment verification. No real application was submitted during the audit.
- Autopilot now enforces company blacklists and per-company daily tier limits in both agents; preferred companies rank first. Numeric priority conditions order queued jobs using recorded scores and listing ages. They do not pre-score every newly scraped listing. Tier counts are checked before processing; simultaneous platforms can race at a cap boundary.
- A lifecycle publisher now sends application.created, application.failed and run.completed for newly recorded outcomes. Delivery is best effort while the API is running; historical outcomes are not replayed on startup. Destination failures are recorded, without guaranteed retry or exactly-once delivery.
- Existing Java/Spring targeting and domain heuristics remain tailored to the repository owner's profile; they are not general-purpose targeting for arbitrary resumes/search terms.
- Seeded multi-platform tests verify source-filtered application totals and recent applications, including excluding pending work from failures. Run logs remain global because their existing schema has no platform column.
- Koyeb's configured filesystem must be persistent to retain accounts, schedules, uploaded resumes and SQLite across redeploys. Repository guidance currently describes ephemeral free-tier storage.

## Deployment

Both backend and frontend must redeploy from the updated branch. The Vercel API rewrite targets the existing Koyeb deployment; change that destination if the backend hostname changes. Keep autopilot disabled and use dry-run while validating platform credentials and resume configuration. Run one application only with the operator's intended submission authorization.
