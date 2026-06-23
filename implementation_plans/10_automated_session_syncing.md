# Implementation Plan: Automated Session Syncing

Ensure the Naukri session cookies never expire by automatically encrypting and pushing the updated session cookies (`session.enc`) back to the GitHub repository at the end of every successful workflow execution.

## Proposed Changes

### CI/CD Component

#### [MODIFY] [auto-apply.yml](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/.github/workflows/auto-apply.yml)

- Grant `contents: write` permission to the `run-bot` job so it can push commits to the repository.
- Add a new step `Encrypt and Commit Session` at the end of the workflow:
  1. Decrypts/re-encrypts the fresh `data/sessions/naukri_session.json` generated during the run into `session.enc`.
  2. Compares the new `session.enc` with the existing one.
  3. If changed, commits and pushes the updated `session.enc` file back to the repository using the default `GITHUB_TOKEN`.

```yaml
    permissions:
      contents: write
```

```yaml
      - name: Encrypt and Commit Session
        env:
          RESUME_KEY: ${{ secrets.RESUME_KEY }}
        run: |
          python -c "
          from cryptography.fernet import Fernet
          import os
          from pathlib import Path
          session_file = Path('data/sessions/naukri_session.json')
          if session_file.exists() and os.environ.get('RESUME_KEY'):
              cipher = Fernet(os.environ['RESUME_KEY'].encode())
              encrypted_data = cipher.encrypt(session_file.read_bytes())
              Path('session.enc').write_bytes(encrypted_data)
              print('Session encrypted successfully.')
          else:
              print('No session file found or RESUME_KEY missing.')
          "
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          if [ -f "session.enc" ] && ! git diff --quiet session.enc; then
            git add session.enc
            git commit -m "Auto-update session cookies [skip ci]"
            git push
          else
            echo "No session changes detected."
          fi
```

## Verification Plan

### Manual Verification
- Commit the workflow changes and push to GitHub.
- Run the workflow manually via `workflow_dispatch` on the GitHub Actions tab.
- Verify that:
  1. The bot runs successfully.
  2. The `Encrypt and Commit Session` step executes, commits the updated `session.enc` (if changed), and pushes it.
  3. No infinite workflow loops are triggered.
