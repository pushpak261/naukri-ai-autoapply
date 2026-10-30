# OpenCode on GitHub

This repository uses the official OpenCode GitHub integration to investigate and fix problems from GitHub itself.

## What runs

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `.github/workflows/opencode.yml` | `/oc` or `/opencode` comment on an issue or pull-request review; manual **Run workflow** | Reads the thread and repository, explains or fixes the problem, and opens a pull request when code changes are needed. |
| `.github/workflows/opencode-ci-autofix.yml` | The `CI` workflow fails on a push to `main` | Collects the failed jobs and dispatches OpenCode with instructions to reproduce, fix, and verify the failure. |

Only comments from the repository owner, organization members, and collaborators can trigger a run. Pull requests opened by OpenCode use the GitHub App token, so the normal CI workflow runs against the fix.

The default model is `opencode/deepseek-v4.1-flash-free`. It costs nothing and needs no model API key. The workflow disables OpenCode session sharing.

## One-time setup

1. Install the OpenCode GitHub App on this repository:

   <https://github.com/apps/opencode-agent>

   Grant it access to `pushpak261/naukri-ai-autoapply`.

2. Make sure the two workflow files are on the `main` branch. The app token exchange uses the workflow's OIDC identity, so no personal access token or model secret is required for the free model.

3. Confirm the app is installed under **Settings → GitHub Apps** in the repository. If a run fails at the token exchange step, the app is usually missing or not granted access to this repository.

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

To run on demand without a comment, open **Actions → OpenCode → Run workflow** and enter the task.

When CI fails on `main`, the autofix workflow dispatches OpenCode automatically. OpenCode opens a pull request with the fix instead of pushing directly to `main`; review it before merging.

## Configuration

Change the model in `.github/workflows/opencode.yml`:

```yaml
with:
  model: opencode/deepseek-v4.1-flash-free
```

The workflow already passes `OPENCODE_API_KEY` from repository secrets when it exists. For a paid OpenCode Zen model, add that secret and change the model id.

For a different provider, add that provider's secret to the workflow's `env` block and use its model id, for example `google/gemini-3-flash` with `GEMINI_API_KEY`.

To stop automatic fixes on `main`, disable or delete `.github/workflows/opencode-ci-autofix.yml`. The comment-triggered workflow is independent.

## Safety notes

- OpenCode runs inside GitHub Actions and only receives the repository contents and the GitHub App token. No Naukri, LinkedIn, Gemini, database, or deployment secrets are passed to the workflow.
- The model can read the repository and run commands in the runner. Keep the collaborator-only trigger in place on a public repository.
- Autofix is limited to failures of the `CI` workflow on pushes to `main`. It does not monitor the scheduled agents, SonarCloud, or deployment failures.
- If CI fails because of missing credentials or an external outage, the prompt tells OpenCode not to change code and to explain the finding instead.
