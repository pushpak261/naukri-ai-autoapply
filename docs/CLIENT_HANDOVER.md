# ApplyOS · client handover

ApplyOS is a workspace for individual job seekers managing a search across Naukri and LinkedIn: resume setup, search preferences, matching, supervised browser runs, application history, and exports. It is built with React/TypeScript and a Python/FastAPI backend, with a navy, teal, and white visual identity. Branding can be adapted for the buyer.

## Deliverables

- Application source, dependency lockfile, and setup instructions.
- Responsive workspace, sign-in and registration, onboarding, and operational pages.
- Resume and preferences management, run controls, logs, history, and available analytics.
- Opportunity Copilot: explainable shortlist, daily action brief, skill priorities and truthful role-preparation drafts. Local rules require no extra API subscription.
- Client acceptance steps using a real account and supervised dry run.
- Account-specific workspaces containing only uploaded profiles, saved platform listings and recorded activity; new accounts start empty.
- Clean source export tool in `scripts/export_client.py`.

The interface exposes existing capabilities. A polished interface does not certify every platform integration or deployment as production-ready. Agree acceptance criteria using the buyer's environment and accounts.

## Install and demonstrate locally

For acceptance, launch the project and register the client's own account. Upload their resume, configure their platform and collect real listings with a supervised dry run. Empty charts are expected before data is collected. No fictional walkthrough is included.

1. Install Python 3.11+ and Node.js 22 LTS, with the Python launcher available on Windows.
2. Double-click `start-local.cmd`. The initial launch installs dependencies and Chromium, builds the frontend, and starts the local dashboard.
3. Register a new local dashboard account. Accounts on other deployments are separate.
4. Upload the client's resume and review the parsed information.
   For AI parsing, first save the client's Gemini key under Preferences → AI Settings and test the connection. Use Reparse with AI to upgrade an older local parse; verify the recorded parsing method and extracted facts.
5. Set role keywords, locations, experience range, and application limits. Review each platform's settings separately.
6. Connect the intended platform. Complete login and any verification manually in the computer's browser.
7. Keep dry-run enabled for the first supervised run. Verify logs and matching decisions before permitting submissions.

### Auto-apply acceptance

The form-flow audit also verifies that optional unknown fields do not block submission, selected answers are preserved, and the chosen resume goes into its own file input. Required non-resume attachments need manual review. Delayed confirmation never triggers a second blind submission. Employer-hosted external forms are explicitly manual; unchecking an older external-skip flag does not establish support for an arbitrary employer form.

Naukri native application forms and LinkedIn Easy Apply use the saved resume and explicit profile settings to answer supported screening fields. The matching toggle does not disable AI screening. Required questions with unknown answers or unmatched choices stop that application for review; the agent does not invent experience, salary, authorization, consent or contact details. Complete those facts in the resume/profile before retrying. External employer sites and platform verification challenges require separate handling.

After a supervised dry run, check the search scope, caps, account/session and resume selection. Disable Dry Run in the intended platform settings only when ready for real submissions. Inspect Applications and run output. Applied requires a platform confirmation; an uncertain submission stops the run and must be checked on the platform before retry. Persisted claims and uncertain outcomes block automatic duplicates after restart. Dry-run and skipped records do not count as confirmed submissions and must not block a subsequent real application.

Automated checks simulate form interactions and verify database behavior. They are not evidence that a live platform accepted a client application. Complete at least one supervised native-form application per contracted platform using the client's own account before accepting that workflow for delivery.

Local data lives in `local-workspace/`. Preserve it privately during upgrades. Back up the workspace with the server and agents stopped; it contains credentials, encryption keys, resumes, and account data. Test restore on a separate computer before relying on the backup. Consult `docs/LOCAL_MOBILE.md` for phone access on private Wi-Fi.

## Rebrand for the buyer

The frontend branding module is in `frontend/src/lib/brand.ts`. Update the product name, tagline, and description there; also review `frontend/index.html`, `frontend/public/favicon.svg`, and the manifest in `frontend/vite.config.ts`. Rebuild with the intended API URL. For the same-origin local setup, set `VERCEL=1` when building so requests use `/api` on the local server. This build flag does not deploy anything.

## Prepare the client source bundle

Run `python scripts/export_client.py`. It creates `artifacts/client/ApplyOS-source.zip` and refuses to overwrite an existing export. Use `--output artifacts/client/ApplyOS-source-v2.zip` for another revision.

The exporter uses an allowlist of project source files, omits runtime folders, resume PDFs, encrypted artifacts, screenshots, logs and developer configuration, and adds fresh configuration templates with dry-run enabled. It includes working-tree source changes; commit and review the intended revision before final release. It is a packaging aid, not a universal secret scanner: inspect the manifest and source content before delivery. Do not give the client the entire development folder or Git history as a substitute for this review. Keep your own configuration and sessions separate from client data.

## Hosting and operations

Local supervised use is the demonstrated deployment path. The single `Dockerfile` starts the API; the repository's Compose setup uses a different multi-service architecture. Do not describe either as interchangeable with the local desktop workflow. Cloud browser verification and storage need a separate acceptance test.

Before a hosted handover, establish HTTPS, persistent data storage, a backup/restore process, dedicated client secrets, resource capacity for Chromium, allowed origins, and operating ownership. A small ephemeral host can lose database files on restart and run out of memory during browser automation. Do not promise availability or capacity based on a local demo. Review `SECURITY.md` and the target platforms' automation rules with the buyer.

## Acceptance record

Record the version/commit, installation date, client device, browser, API address, and test account used. Agree and demonstrate:

- Registration, login, logout, and session restoration.
- Dashboard loading after a refresh and at phone width.
- Resume upload, parsed fields, and configuration persistence.
- A supervised dry run for each platform in the contracted scope.
- Stop control, readable failure messages, and run logs.
- Application history and exports where data exists.
- Restart persistence and backup restoration.
- Exclusion of the seller's credentials, resume, sessions, and account data from delivery.

Do not mark items complete without evidence. Keep client screenshots and personal data out of the source bundle.

## Commercial scope to agree

### Supervised Naukri validation — 2026-10-18

A supervised Dry Run restored the saved Naukri login and scraped 51 real listings. Experience filtering now retains ranges such as 0-4 years when junior applicants meet the minimum requirement. The agent reused a validated AI profile for the same resume hash without a fresh parsing request. Gemini's daily quota blocked the first AI job assessment, so screening and submission were not validated live and no Naukri applications were submitted. Quota failures stop clearly without silently replacing the AI profile with local parsing. Agent cleanup closes the AI client as well as the browser. The UI's explicit AI reparse still requests a fresh parse.

### Supervised LinkedIn validation — 2026-10-18

With the account owner's approval for one real application, a single queued Pune role passed Gemini matching at 85/100. The agent restored the saved session, uploaded the selected resume, preserved prefilled contact fields, filled screening fields, reached review and received platform submission confirmation. Both application history and the completed run recorded one applied job and zero failures. Original Dry Run mode and the daily cap were restored afterward. This verifies that particular LinkedIn Easy Apply flow; Naukri and other employers' forms still require their own live acceptance checks.

Live validation identified and fixed truncated Gemini output, duplicate resume-hash inserts on restart, and hidden duplicate Apply button selection. Queueing now preserves uncertain submission records for review. The complete regression suite passed 1,117 tests with one Windows symlink skip; subsequent targeted checks passed after the final selector and screening-prompt edits. Personal logs and screenshots remain outside the client source export.

### Gemini AI features

Career Studio is available in Opportunity Copilot and saved job details. Application packs include resume rewrite suggestions and cover-letter drafts with exact source quotes checked against saved evidence. Interview rehearsals contain role-specific questions and on-demand feedback on the client's own answers. Seven-day search plans contain one task for each day, based on saved roles. Generated work persists in the signed-in workspace and can be reopened and exported as Markdown. Questions and evidence reflect the saved generation context; regenerate after changing a resume or listing. Practice answers are sent to Gemini on request for feedback and are not saved in artifact history. These tools do not submit applications, send outreach or overwrite the resume.

Missing keys, resumes, listings, invalid model output and unsupported source quotes produce explicit errors rather than fictional artifacts. Quote validation establishes that a quote appears in the source; it does not certify the truth or relevance of every generated claim. Review before client use. Generated artifacts live under the account data/career_studio directory and are excluded from the client source ZIP. Export important work as Markdown.

Save a client-owned Gemini key under Preferences. Resume parsing, agent matching and screening use shared AI settings. The Gemini AI advisor on relevant workspace pages provides on-demand resume reviews, learning plans, listing comparisons, application strategy, saved-market interpretation, risk reviews, analytics explanations and agent-setting suggestions. Job-detail advice uses the selected saved listing. Other reviews use up to 20 recent listings and 100 recent application statuses, not live market research. Relevant profile/listing details are sent to Gemini only on request. Generated advice never applies, sends outreach or changes settings automatically. AI errors remain visible.

Measured charts, rule-based coverage and risk signals remain separate from Gemini advice. Platform sign-in, verification challenges and a supervised client-account dry run remain acceptance checks. Earlier Gemini structured-output checks used isolated fictional test fixtures. The supervised LinkedIn validation below used the account owner's real data and explicit one-application approval.

Separate the software handover from installation, client branding, migration, platform verification, hosting, maintenance, and training. Define supported devices and platforms, acceptance criteria, included support period, response expectations, and how platform changes are handled. Confirm the rights and dependency licenses for anything you transfer. This repository does not itself establish exclusive ownership or a commercial license agreement.

Promise working features and measurable acceptance tests. Interview rates, job offers, time savings, uninterrupted automation, multi-tenant agency administration, billing, and support SLAs need their own evidence or implementation before being sold as capabilities.


### Hosted login durability

Mount durable storage, then set `DASHBOARD_DATA_DIR` to that mounted directory. Back up and migrate the existing directory before changing this variable: it contains `dashboard_identities.db`, per-user workspaces in `users/`, and the generated JWT secret when no explicit secret is configured. Preserve `JWT_SECRET` and `SESSION_ENCRYPTION_KEY` across restarts using the hosting secret manager. Do not put values in Git. A restart on ephemeral storage may lose registered users and revoke sessions.

Agent startup checks the Linux container RAM limit. The default protective budget reserves 256 MiB for the API plus 768 MiB per browser agent, so a 512 MiB deployment cannot start browser automation. Provision more memory and persistent storage, or run agents locally. Capacity still needs live load testing for the chosen deployment.


### Run the agents without Gemini

In Preferences, turn off Use Gemini AI and save. Both agents use a no-network provider, shared skill/role scoring, eligibility checks, and factual screening answers. Resume uploads follow this setting and can extract locally; always review extracted fields. Fill CTC, notice period, location, total experience, and the Gemini-free assistant's skill experience and confirmed-answer bank. Unknown required declarations or employer-specific questions block submission for review; they are never guessed. Supported numeric answers include decimal tenure, months, salary ranges and explicit LPA-to-INR conversion. Keep Dry Run enabled for validation; switch it off only when ready for real applications. Native Naukri forms and LinkedIn Easy Apply retain attachment checks, duplicate protection, and single-submit confirmation. External employer forms and CAPTCHA/OTP require manual action. This rules-based mode is not a local generative AI model.
