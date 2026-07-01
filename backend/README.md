# Backend — Naukri AI Agent + FastAPI API

Python agent (CLI + Playwright automation) and HTTP API for the React dashboard.

## Install

```bash
cd backend
pip install -r requirements.txt
playwright install chromium

# Optional — tests, lint, pre-commit
pip install -r requirements-dev.txt
pre-commit install -c .pre-commit-config.yaml
```

## Agent CLI

Run all commands from the `backend/` directory with `PYTHONPATH=.`:

```bash
# PowerShell
$env:PYTHONPATH="."

# bash / macOS / Linux
export PYTHONPATH=.

python -m src.naukri_agent.main init
python -m src.naukri_agent.main run --dry-run
python -m src.naukri_agent.main run
python -m src.naukri_agent.main status
python -m src.naukri_agent.main refresh-profile
```

Or use the Makefile: `make init`, `make run`, `make test`, `make lint`.

### Configuration

- `config.yaml` — job search preferences, application controls
- `.env` — credentials (created by `init` from `.env.example`)
- `data/` — SQLite database, sessions, logs (gitignored)

## FastAPI dashboard API

From the **repository root** (no `PYTHONPATH` needed):

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 --loop backend.loop:create_event_loop
```

API docs: http://127.0.0.1:8000/api/docs

From `backend/`: `make dev-api`

## Utility scripts

Run from `backend/`:

| Script | Purpose |
|--------|---------|
| `python scripts/decrypt_secrets.py` | Decrypt `resume.pdf.enc`, `resume_profile.json.enc`, `session.enc` for local dev |
| `python scripts/update_resume.py` | Encrypt `resume.pdf` for GitHub Actions deployment |
| `python scripts/sync_session.py` | Encrypt local Naukri session cookies for cloud runs |

## Development

```bash
cd backend
$env:PYTHONPATH="."

pytest
pytest --cov=src --cov-report=term-missing
ruff check src tests
black src tests
mypy src
```

CI runs these checks via `.github/workflows/ci.yml` with `working-directory: backend`.

## Layout

```text
backend/
  src/naukri_agent/   # Core agent (config, ai, browser, database, orchestrator)
  routes/             # FastAPI REST + SSE endpoints
  services/           # RunManager, event bus
  schemas/            # Pydantic API models
  scripts/            # decrypt_secrets, update_resume, sync_session
  tests/              # Agent + API unit tests
  docs/               # SECURITY.md, CODE_REVIEW.md
  data/               # Runtime SQLite, logs (gitignored)
  config.yaml
  main.py             # FastAPI app factory
```

## Cloud deployment (GitHub Actions)

Encrypted secrets (`resume.pdf.enc`, `session.enc`) live in `backend/`. Workflows in `.github/workflows/` run with `working-directory: backend`.

1. Place `resume.pdf` in `backend/`, then run `python scripts/update_resume.py`
2. Add GitHub secrets: `GEMINI_API_KEY`, `NAUKRI_EMAIL`, `NAUKRI_PASSWORD`, `RESUME_KEY`
3. Scheduled workflows: `auto-apply.yml`, `profile-refresh.yml`

To sync session cookies from a local login: run the agent locally, then `python scripts/sync_session.py` and commit `backend/session.enc`.

See [docs/SECURITY.md](docs/SECURITY.md) before running against a real account.
