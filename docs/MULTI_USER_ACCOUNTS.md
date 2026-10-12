# Separate dashboard accounts

Dashboard registration now creates a distinct identity, independent of Naukri and LinkedIn credentials. The existing operator is migrated once from the configured Naukri login and keeps the original workspace. Changing platform credentials subsequently does not change the dashboard password.

Each new user gets a private SQLite database, configuration, resumes, platform sessions, backups, logs, and agent state under `DASHBOARD_DATA_DIR/users/<random-id>`. New accounts start with dry-run enabled, no platform or AI credentials, and resume-based targeting. Connect platform credentials and upload a resume before starting an agent.

Passwords use salted PBKDF2-SHA256. Access tokens expire after 15 minutes. Refresh cookies are Secure, HttpOnly, SameSite=Lax, rotate on use, and are revoked on logout. Platform passwords are encrypted using the deployment's `SESSION_ENCRYPTION_KEY`. Keep that key stable across deployments.

## Deployment

- `OPEN_REGISTRATION=true` enables signup (the default); `false` disables new registrations while existing users can still log in.
- Set `DASHBOARD_DATA_DIR` to a **mounted persistent directory**. It stores the identity database, generated signing secret, and new users' workspaces. Without durable storage, the existing Koyeb free-tier ephemeral filesystem loses accounts and data on redeployment. This code change does not provision a volume or change the hosting plan.
- Keep `JWT_SECRET` and `SESSION_ENCRYPTION_KEY` stable. Existing operator paths retain their original configuration.
- Run one API worker: agent ownership, browser capacity, and schedulers are in-process. Horizontal scaling requires a shared job coordinator and durable databases.
- `MAX_ACTIVE_AGENTS` limits total browser processes across users (default 2). Choose 1 on a small instance; Chromium may exceed a 512 MB instance's available memory.
- `DASHBOARD_ALLOWED_ORIGINS` is a comma-separated allowlist. The default production frontend and local development origins are allowed. Vercel's same-origin `/api` proxy supports refresh cookies without third-party cookies.

## Validation

Regression tests cover independent registration, duplicate addresses, hashed passwords, refresh rotation/replay/logout, concurrent requests from two identities, isolated platform accounts/configuration/resumes/exports, deletion boundaries, private-network webhook rejection, and fresh-user agent validation. Browser checks exercise registration, authenticated navigation, account CRUD, configuration persistence, backup create/restore, exports, resume upload/edit, webhook create/delete, and logout/login.

Real Naukri/LinkedIn login and application submission, Gemini calls, and webhook delivery require the user's configured external accounts/services. Dummy dashboard accounts alone do not verify these external integrations. No real applications are submitted by the dummy-account test.
