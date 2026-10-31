# ApplyOS

A focused job-search workspace for individual job seekers. Manage your resume, preferences, Naukri and LinkedIn workflows, application history, and analytics through a responsive React dashboard backed by FastAPI.

## Run locally on Windows

Install Python 3.11+ with the Python launcher and Node.js 22 LTS. Double-click `start-local.cmd` from the project folder.

The launcher creates a virtual environment, installs Python dependencies and Chromium, builds the dashboard, and starts the local server at **http://localhost:8005**. Keep the launcher running while using the app.

1. Register a local dashboard account.
2. Upload your resume and review your profile.
3. Set role keywords, locations, experience, matching threshold, and a daily cap.
4. Configure the intended platform. Naukri and LinkedIn have separate settings and sessions.
5. Start with **dry run** enabled. Complete any sign-in or verification manually on the computer.
6. Review matches and logs before permitting live submissions.

For phone access on the same private Wi-Fi, use the URL printed by the launcher. See [Local and mobile setup](docs/LOCAL_MOBILE.md).

## Real workspace data

Client workspaces start empty. Jobs, activity and charts come from that account's saved platform searches and application records. Missing data stays empty or shows N/A. No fictional demo is included. Dry run searches real listings without submitting applications.

## Workspace

| Area | Purpose |
| --- | --- |
| Overview | Real activity totals, setup checks, recent runs, and exports |
| Discover jobs | Browse and inspect collected opportunities |
| Opportunity Copilot | Evidence-based shortlist, daily action brief, skill priorities and role preparation |
| Resume & profile | Upload and review resume information |
| Preferences | Configure search, profile answers, and application limits |
| Command center | Control runs and inspect Naukri session status |
| LinkedIn workspace | Manage LinkedIn settings and operations |
| Applications | Review application history and status |
| Intelligence | Analytics, market tools, skill analysis, and job inspection |
| Operations | Logs, backups, cache, webhooks, and data management |
| Getting started | Setup walkthrough and common questions |

AI features can use Google Gemini when configured. Automation assists a supervised job search and does not guarantee applications, interviews, or offers.

### Run both agents without Gemini

Leave **Use Gemini AI** off in Preferences. No AI API key is needed for job discovery, local resume parsing, matching, or filling supported screening fields. Both platforms use the same reviewed resume and saved profile facts; LinkedIn inherits shared search keywords and locations unless you save platform-specific overrides.

Upload a PDF or DOCX, review the extracted profile, and save your search targets. In **Experience by skill**, enter your actual tenure for each technology; a skill listed in a resume does not establish its duration. Use **Confirmed screening answers** for recurring questions, and save salary, notice period, location, and total experience where known. Unknown required answers stop that application for review rather than inventing personal details.

Connect each platform and start with **Dry Run** enabled. Search visits all configured keyword/location combinations within the page limit, while the daily cap limits submissions. After reviewing the results and your facts, disable Dry Run to submit matching applications through Naukri native forms and LinkedIn Easy Apply. External employer forms, authentication challenges, and unsupported questions require manual review.

For a LinkedIn `Remote` search target, set `search.remote_location` in the workspace's `linkedin_config.yaml` to the intended country or region (for example, `India`). This applies the Remote work filter across that region. When blank, LinkedIn's currently selected geography is retained.

Naukri persists discovered listings after every completed page. Set `search.required_title_keywords` in the workspace configuration to restrict role titles independently of ranking. Experience limits use the stated minimum and units; reviewed candidate experience and explicit description requirements are checked before applying. Unknown screening answers are recorded for review. A submission needs platform confirmation, including Naukri's current `Applied` status; an uncertain result is checked by reading the listing again and is never resubmitted automatically. Email reports respect the email-notification setting.

Job highlights are included in requirement checks, and concrete stack requirements in the description complement listing tags. Chatbot questions are read from the active message panel, including nested contenteditable inputs. Save and Submit actions stay inside the active form and respect disabled controls and ancestors; the agent does not enable controls or click a listing's Save button to advance screening.

With Gemini disabled, Naukri resolves screening questions from saved facts, confirmed answers, resume introductions/projects and a local bank of common technical explanations. It collects unknown questions in **Applications → Screening answers** before saving or submitting an incomplete form, including unanswered optional text questions. Confirm an answer once and it is reused for the same question and units; company-specific answers stay scoped to that job. **Save and retry ready jobs** queues only jobs whose collected questions are resolved, while applied or uncertain applications remain protected against repeated submissions. Learning is stored privately in the user's `data/screening_review.db`; preserve that file with the user's workspace backup.

Set employment status and whether notice is currently being served in Preferences. A notice duration does not establish a resignation date: someone employed and not serving notice receives a truthful "not fixed" answer in text fields. A mandatory date control still needs a confirmed date. Unsupported questions, declarations and attachments require the user's input instead of invented facts.

External employer forms with supported repeatable Education Details and Experience Details sections now add one row per saved resume record. Institutions, degrees, stated majors, employers, titles, responsibilities and date components stay scoped to their own records. Ongoing employment uses the employer's current-employment control. Missing dates or streams appear in Screening answers before submission; month/year evidence never becomes an invented daily date. Dry Run fills and validates these sections without clicking Next or Submit. This shared flow serves external applications from both agents.

### Opportunity Copilot

Open `/copilot` after saving your profile and collecting jobs. Copilot reviews up to 500 recent listings, explains structured skill overlap, flags location or stated-experience mismatches, and suggests practical next steps. A role preparation brief provides evidence-grounded talking points, recruiter questions, a checklist and an editable outreach starting point. It never sends messages or queues applications.

Copilot runs locally without an additional API key. Its evidence score is skill coverage, not an AI match score or hiring probability. Both application agents also use a small resume-skill evidence boost to order otherwise eligible jobs; existing filters, AI scoring, daily limits and submission checks still apply.

## Data and accounts

### Set up real AI parsing and matching

Open **Preferences → AI Settings**, enter your own Gemini API key, enable Gemini and matching, and save. These AI preferences are shared by Naukri and LinkedIn. Use **Test saved AI connection** to verify model access without sending a resume. The default is `gemini-2.5-flash`.

On **Resume & profile**, upload a file or choose **Reparse with AI** for an existing upload. The AI-only path validates structured output, records the model, bypasses old local parses, and preserves the previous profile on failure. Provider failures and missing keys are shown explicitly. Resume requests have a longer timeout than ordinary API reads. Review extracted facts before running agents.

Screening answers use candidate evidence and configured preferences. Unknown or unsupported answers require review; they must not be replaced with guessed eligibility or personal details. Analytics and Opportunity Copilot evidence scores remain measured/rule-based features, not language-model predictions. Live AI acceptance requires a valid key, network access and available provider quota.

The local launcher keeps account data, resumes, encrypted sessions, and keys in `local-workspace/`, excluded from Git. Preserve and back up this folder privately when updating the code. Local accounts and cloud accounts are separate.

Never include your development workspace, credentials, sessions, resume, or Git history in a client delivery without reviewing its contents. Browser verification must be performed by the account owner. Review [Security and platform considerations](SECURITY.md).

## Client presentation and delivery

- [Client handover](docs/CLIENT_HANDOVER.md): installation, branding, acceptance criteria, operations, and delivery scope.
- `python scripts/export_client.py`: creates `artifacts/client/ApplyOS-source.zip` from an allowlist of source files, with clean configuration templates and no developer runtime folders.

The exporter refuses to overwrite an existing archive. Use `--output artifacts/client/ApplyOS-source-v2.zip` for a later revision. Review the manifest and source before delivery; packaging is not a complete secret or license audit.

## Development

Frontend: React, TypeScript, Vite, Tailwind CSS, Redux Toolkit, TanStack Query. Backend: Python, FastAPI, SQLAlchemy, SQLite/PostgreSQL support, Playwright, and optional Gemini integration.

```powershell
# Backend dependencies
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python -m playwright install chromium

# Frontend development server; /api proxies to localhost:8005
cd frontend
npm ci
npm run dev

# Frontend production checks
npm run build
npm run lint
```

For the same-origin local dashboard build, set `VERCEL=1` before `npm run build`, then run `.venv\Scripts\python scripts/local_dashboard.py` from the project root. The Windows launcher handles this automatically. The build flag selects relative API requests; it does not deploy the project.

```powershell
# Run backend tests from the root
.venv\Scripts\python -m pytest

# Verify client export exclusions
.venv\Scripts\python -m pytest tests/test_client_export.py -q
```

The CLI remains available through `python -m src.naukri_agent.main`; use `--help` for commands. For a scoring preview, use `run --dry-run` with the intended configuration.

## Automated bug fixing

OpenCode runs in GitHub Actions and can fix CI, SonarCloud, and scheduled-agent failures, `bug`-labeled issues, failures found by a daily whole-repository health audit, a failed production health endpoint, and exception reports from an external monitor. It opens pull requests for review. See [OpenCode on GitHub](docs/OPENCODE_GITHUB.md) for setup and usage.

## Hosting

The local desktop workflow, the API-only `Dockerfile`, and the multi-service `docker-compose.yml` are distinct deployment paths. Validate the intended deployment before promising client compatibility. Hosted operation requires appropriate secrets, HTTPS, persistent storage, backups, and enough memory for Chromium. Ephemeral hosting can lose SQLite data on restart.

See the [client handover guide](docs/CLIENT_HANDOVER.md) for deployment acceptance checks. No cloud resources or paid services are provisioned by the local launcher.
