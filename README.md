# Naukri.com AI Job Application Agent

AI-powered agent that discovers and applies to relevant jobs on Naukri.com, with a React dashboard for live monitoring.

## Repository layout

```text
backend/    Python agent (CLI + Playwright) and FastAPI dashboard API
frontend/   React dashboard (Vite + TypeScript)
```

## Quick start

### Backend (agent CLI)

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
pip install -r requirements-dev.txt   # optional, for tests/lint

$env:PYTHONPATH="."                   # PowerShell; bash: export PYTHONPATH=.
python -m src.naukri_agent.main init
python -m src.naukri_agent.main run --dry-run
```

See [backend/README.md](backend/README.md) for full CLI commands, utility scripts, and API setup.

### Frontend (dashboard)

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 (proxies `/api` to the backend on port 8000). See [frontend/README.md](frontend/README.md).

### Full stack development

```bash
# Terminal 1 — API (from repo root)
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 --loop backend.loop:create_event_loop

# Terminal 2 — UI
cd frontend && npm run dev
```

## Documentation

| Topic | Location |
|-------|----------|
| Agent CLI, API, scripts, cloud deploy | [backend/README.md](backend/README.md) |
| React dashboard | [frontend/README.md](frontend/README.md) |
| Security & ethics | [backend/docs/SECURITY.md](backend/docs/SECURITY.md) |

## License

Personal, educational use only. Use responsibly.
