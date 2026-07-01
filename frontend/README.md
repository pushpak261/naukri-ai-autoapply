# Frontend — React Dashboard

Vite + React + TypeScript dashboard for starting/stopping the agent and viewing live job progress.

## Install

```bash
npm install
```

## Run

Start the API first (from repo root — see [backend/README.md](../backend/README.md)), then:

```bash
npm run dev
```

Open http://127.0.0.1:5173 (proxies `/api` to the backend on port 8000).

## Layout

```
frontend/
  src/
    api/         # REST client
    app/         # Router, providers
    components/  # Shared UI (shadcn-style)
    features/    # Dashboard, jobs, history, settings
    hooks/       # SSE event stream
    store/       # Zustand live state
```
