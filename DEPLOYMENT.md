# Vercel dashboard and Python agent

The Vercel deployment serves the React dashboard. It does not start the Python
API, database, scheduler, or Playwright browser. Run the repository Dockerfile
on a persistent backend host, such as Koyeb, and keep that service running.

## Configure both services

1. In Vercel, set the project root to `frontend`, build command to `npm run build`,
   and output directory to `dist`.
2. Set `VITE_API_BASE_URL` to your Python backend HTTPS origin (or its `/api`
   endpoint). This is a build-time variable: redeploy the dashboard after changes.
   Never put passwords, dashboard API keys, or Gemini keys in `VITE_*` variables.
3. Configure the backend with `NAUKRI_EMAIL`, `NAUKRI_PASSWORD`, `JWT_SECRET`,
   `SESSION_ENCRYPTION_KEY`, `JWT_ENCRYPTION_KEY`, and `GEMINI_API_KEY`.
   Keep encryption/signing keys stable across restarts. `HEADLESS=true` is
   already set in the Docker image. A configured `DASHBOARD_API_KEY` accepts
   either that operator key or the dashboard's signed access JWT.
4. Persist the backend data directory and configuration files across restarts.
   SQLite, resumes, browser sessions, backups, and autopilot settings otherwise
   disappear on redeploy. Use persistent storage or the supported database setup.
5. Sign in with the configured Naukri credentials. Login does not validate
   credentials against Naukri itself; it authenticates the dashboard against
   the operator's configured account. Initial registration requires an explicit
   `OPEN_REGISTRATION=true` and no existing configured account. Disable it after
   setup. Adding additional automation accounts is done on the Accounts page.

## Refresh cookies

Refresh requires the browser's HTTP-only cookie. Browsers that block third-party
cookies may prevent renewal when Vercel calls a separate backend domain. Prefer
a same-origin API reverse proxy (all `/api/*` methods, uploads, cookies, and SSE),
or place dashboard/backend under the same site. With a same-origin proxy, leave
`VITE_API_BASE_URL` empty. The included SPA fallback excludes `/api/*`; add the
backend proxy rule before that fallback. Never serve `index.html` for API calls.

## Verify the deployed features

- Confirm backend `/api/health` returns JSON and its database check is `ok`.
- Confirm dashboard `/login`, `/jobs`, and other deep links survive reload.
- Check successful login, rejected incorrect credentials, logout, and renewal
  after 15 minutes. Anonymous requests must not acquire another user's session.
- Upload a resume, save preferences, and verify both survive a backend restart.
- Exercise Jobs, Applications, Analytics, Market Intelligence, Scam Detector,
  Skills Gap, Accounts, Cache, Logs, Backups, and export/import with real data.
- Start a **dry-run** agent and verify live logs, status, and stop. Ensure
  Playwright can launch Chromium with the host's memory budget.
- Confirm Naukri/LinkedIn login and any OTP/CAPTCHA requirements separately.
  A dashboard fix cannot establish a valid external account session.
- Test scheduling and application submissions only after the dry run succeeds.

## Validation commands

```sh
cd frontend
npm ci
npm run build
npm run lint
node --test tests/api.test.mjs
cd ..
python -m unittest tests.test_dashboard_auth_regressions
pytest
```

Node 24+ can run the API regression tests using built-in TypeScript stripping.
