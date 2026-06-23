# Resume Profile Synchronization Plan

This plan details why the parsed resume profile differs between your local environment and the remote GitHub Actions runner, and outlines the proposed changes to unify them.

## Why the Resume Profile is Different

There are three main reasons why the parsed resume profile differs between environments:

1. **Independent local SQLite databases**: The SQLite database (`data/naukri_agent.db`) caches parsed resume profiles to avoid repeated Gemini API calls. However, your local machine and the remote GitHub Actions runner maintain **separate SQLite database files**.
2. **Platform-specific OCR differences**: Your resume PDF does not have a native text layer (it is scanned/image-only). The parser falls back to Tesseract OCR, which is installed on different platforms (Windows locally vs. Ubuntu in GitHub Actions). Minor rendering differences and OCR version differences result in slightly different extracted text inputs sent to Gemini.
3. **Generative AI Non-determinism**: Because the text inputs differ slightly and generative LLMs (Gemini) are inherently non-deterministic, the model extracts slightly different years of experience and lists of skills for the same resume. These differing parsed profiles are then stored in their respective database caches.

---

## Proposed Changes

To fix this, we will introduce a version-controlled, encrypted parsed resume profile file (`resume_profile.json.enc`). This mirrors how `resume.pdf.enc` is handled:

1. The local run will automatically save/read a plaintext `resume_profile.json` file in the project root.
2. The user can review and edit `resume_profile.json` to manually tweak skills or experience if needed.
3. Running `update_resume.py` will encrypt `resume_profile.json` to `resume_profile.json.enc` using the same key as the resume.
4. The remote workflow will decrypt `resume_profile.json.enc` back into `resume_profile.json`.
5. The resume parser will load `resume_profile.json` directly if it exists, completely bypassing Gemini API and OCR calls, guaranteeing identical matching behavior.

### Configuration & Git ignores

#### [MODIFY] [.gitignore](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/.gitignore)
- Add `resume_profile.json` to prevent raw personal information from being accidentally pushed to Git in plaintext.

---

### Resume Parser

#### [MODIFY] [resume_parser.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/ai/resume_parser.py)
- Modify `ResumeParser.parse()` to:
  1. Check if `resume_profile.json` exists in the root directory. If it does, load and return it immediately.
  2. If it does not exist, parse using the database/Gemini flow, and then save the resulting JSON to `resume_profile.json` so the user can inspect/edit it locally.

---

### Encryption Utilities

#### [MODIFY] [update_resume.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/update_resume.py)
- Add logic to encrypt `resume_profile.json` into `resume_profile.json.enc` using the key in `resume_key.txt`.

---

### CI/CD Workflows

#### [MODIFY] [auto-apply.yml](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/.github/workflows/auto-apply.yml)
- Update the decryption step to also decrypt `resume_profile.json.enc` to `resume_profile.json` on the runner if the encrypted file exists.

---

## Verification Plan

### Automated Tests
- Run `python -m src.main run` locally and verify that:
  - A local `resume_profile.json` is generated or loaded.
  - No new Gemini API call is made if `resume_profile.json` is loaded.

### Manual Verification
- Run `python update_resume.py` to encrypt the profile.
- Verify `resume_profile.json.enc` is created.
- Verify that both local and remote runs use the exact same resume profile data.
