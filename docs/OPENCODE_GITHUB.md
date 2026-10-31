# OpenCode on GitHub

This repository uses the official OpenCode GitHub integration to find and fix problems across the whole application, not just one workflow.

## What runs

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `.github/workflows/opencode.yml` | `/oc` or `/opencode` comment on an issue or pull-request review; manual **Run workflow** | Reads the thread and repository, explains or fixes the problem, and opens a pull request when code changes are needed. |
| `.github/workflows/opencode-ci-autofix.yml` | `CI`, `SonarCloud Analysis`, `Naukri Auto Apply Cron`, or `Naukri Profile Refresh Cron` fails or times out on `main` | Dispatches OpenCode with the failed jobs and instructions to reproduce, fix, and verify the failure. |
| `.github/workflows/opencode-bug-issues.yml` | A maintainer opens a `bug` issue, or adds the `bug` label to an existing issue | Dispatches OpenCode with the full bug report. It fixes the root cause and opens a pull request, or comments with findings if the report is not reproducible. |
| `.github/workflows/opencode-health-audit.yml` | Daily at **09:00 IST**; manual **Run workflow** | Runs the whole-repository audit. If a hard check or the audit setup fails, it dispatches OpenCode to fix the failures. |
| `.github/workflows/opencode-production-health.yml` | Every 30 minutes; manual **Run workflow** | Checks `PRODUCTION_HEALTH_URL`. If the deployed app is down, it dispatches OpenCode once per outage. Inactive until the variable is set. |
| `.github/workflows/opencode-production-error.yml` | A `production-error` repository dispatch | Accepts an exception report from Sentry or another monitor and dispatches OpenCode. Inactive until a monitor sends an event. |

The workflows instruct OpenCode to open pull requests for review; nothing is intentionally pushed directly to `main`.

## What the health audit checks

Hard failures trigger an OpenCode fix:

- Hardening ruff gate and `black --check libs`
- Full Python test suite
- Browser regression suite (offline Naukri, LinkedIn, screening, external application flows)
- Frontend lint
- Frontend production build
- Frontend API tests

Advisory checks are reported but do not trigger a fix:

- Full-repository `ruff check .`
- `mypy src/`

The repository intentionally carries pre-existing ruff and mypy debt; the required CI gates still pass. Keeping those checks advisory avoids a daily flood of unrelated cleanup pull requests. To clean that debt deliberately, comment on an issue with `/oc fix the ruff and mypy debt in small reviewed batches` or run a manual workflow with that prompt.

## One-time setup

1. Install the OpenCode GitHub App on this repository:

   <https://github.com/apps/opencode-agent>

   Grant it access to `pushpak261/naukri-ai-autoapply`.

2. Make sure the workflow files are on `main`. The app token exchange uses the workflow's OIDC identity, so no personal access token is required.

3. Confirm the app is installed under **Settings → GitHub Apps** in the repository. If a run fails at the token exchange step, the app is usually missing or not granted access to this repository.

4. Optional: set a repository variable named `PRODUCTION_HEALTH_URL` under **Settings → Secrets and variables → Actions → Variables**. Use a public endpoint such as `https://your-app.koyeb.app/api/health`. The production health workflow stays inactive until this is set.

5. Optional: make sure the `bug` label exists under **Issues → Labels**. The repository already has it.

## Usage

On any issue or pull-request review comment:

```text
/oc explain this failure
```

```text
/oc fix this and add a regression test
```

On a pull request where CI failed:

```text
/oc investigate the failing CI job and fix the root cause
```

To fix a reported bug automatically, add the `bug` label to the issue. OpenCode reads the report, investigates, and opens a pull request. A comment confirms when it has been dispatched. Maintainers can also open an issue with the `bug` label directly.

To run on demand without a comment, open **Actions → OpenCode → Run workflow** and enter the task. To run the full audit on demand, use **Actions → OpenCode Health Audit → Run workflow**.

## Production error hook

`opencode-production-error.yml` accepts a `repository_dispatch` event named `production-error`. Point Sentry, a log alert, or any monitor at GitHub's dispatch API:

```bash
curl -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/pushpak261/naukri-ai-autoapply/dispatches \
  -d '{
    "event_type": "production-error",
    "client_payload": {
      "service": "api",
      "environment": "production",
      "url": "https://your-app.example/api/health",
      "error": "Unhandled exception while starting an agent",
      "stack": "Traceback ..."
    }
  }'
```

The token needs permission to write repository contents (classic `repo` scope or a fine-grained token with **Contents: write**). Store it only in the monitor's secret store; never put it in a workflow file or issue. The workflow treats the error text as untrusted data and tells OpenCode not to follow instructions inside it.

## Configuration

Change the model in `.github/workflows/opencode.yml`:

```yaml
with:
  model: opencode/deepseek-v4.1-flash-free
```

The workflow already passes `OPENCODE_API_KEY` from repository secrets when it exists. For a paid OpenCode Zen model, add that secret and change the model id.

For a different provider, add that provider's secret to the workflow's `env` block and use its model id, for example `google/gemini-3-flash` with `GEMINI_API_KEY`.

Change the audit time in `.github/workflows/opencode-health-audit.yml`:

```yaml
schedule:
  - cron: '30 3 * * *'   # 09:00 IST
```

Change the production check interval in `.github/workflows/opencode-production-health.yml`:

```yaml
schedule:
  - cron: '*/30 * * * *'   # every 30 minutes
```

To stop a component, disable its workflow under **Actions** or delete the file:

- `opencode-ci-autofix.yml` — automatic fixes after CI, SonarCloud, or scheduled-agent failures
- `opencode-bug-issues.yml` — automatic fixes for `bug`-labeled issues
- `opencode-health-audit.yml` — daily whole-repository audit
- `opencode-production-health.yml` — production endpoint monitoring
- `opencode-production-error.yml` — exception reports from Sentry or another monitor

## Limits

- The automation can only detect problems it can observe: failed tests, browser flows, lint/build errors, Sonar failures, CI failures, scheduled-agent workflow failures, labeled bug reports, and a failed production health endpoint.
- The production health workflow detects a down endpoint, not every runtime exception. Exception-level reports need an error tracker wired to the `production-error` repository dispatch hook; the repository does not configure Sentry or a monitor for you.
- It does not read Koyeb or Vercel logs directly. Add the deployment URL to `PRODUCTION_HEALTH_URL` so outages are visible.
- Naukri/LinkedIn login failures, OTP prompts, captchas, session expiry, and platform blocks are not code bugs. The scheduled-agent autofix explicitly reports those instead of guessing at a code change.
- External failures are reported instead of guessed at. The prompt explicitly tells OpenCode not to change code for missing credentials, outages, or flaky network failures.
- Every fix is a pull request and must be reviewed. Automatic fixes can be wrong, especially for agent/browser behavior that depends on live platforms.
- The free model is rate-limited. Add `OPENCODE_API_KEY` if runs are slow or queued.

## Safety notes

- Only the repository owner, members, and collaborators can trigger comment-based runs.
- Only maintainers can label an issue `bug`. An outside reporter cannot trigger a fix by opening an issue with a template-applied label; the workflow checks the issue author's association for the `opened` event.
- OpenCode runs inside GitHub Actions and receives only the repository contents and the GitHub App token. No Naukri, LinkedIn, Gemini, database, or deployment secrets are passed to the workflow.
- Bug reports are treated as untrusted data: the prompt tells OpenCode to ignore requests to reveal secrets, change permissions, or disable checks.
- Keep the collaborator-only trigger and the `bug`-label check in place on a public repository.
