"""
Encrypt resume.pdf (and optional resume_profile.json) for cloud deployment.

On first run, generates resume_key.txt. On later runs, reuses the existing key
so GitHub Secrets do not need to change.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cryptography.fernet import Fernet

from src.naukri_agent.utils.secrets import encrypt_file, generate_and_save_key, load_fernet_key


def main() -> None:
    resume_path = PROJECT_ROOT / "resume.pdf"
    enc_path = PROJECT_ROOT / "resume.pdf.enc"

    if not resume_path.exists():
        print("[ERROR] resume.pdf not found in the backend directory.")
        print("Place your PDF resume there, then run this script again.")
        sys.exit(1)

    key = load_fernet_key(PROJECT_ROOT)
    key_was_new = key is None
    if key_was_new:
        key = generate_and_save_key(PROJECT_ROOT)
        print("[NEW] Generated resume_key.txt — add this value as the RESUME_KEY GitHub secret.")
    else:
        print("[INFO] Using existing resume_key.txt")

    cipher = Fernet(key)
    encrypt_file(resume_path, enc_path, cipher)
    print("[SUCCESS] Encrypted resume.pdf → resume.pdf.enc")

    profile_path = PROJECT_ROOT / "resume_profile.json"
    profile_enc_path = PROJECT_ROOT / "resume_profile.json.enc"
    if profile_path.exists():
        encrypt_file(profile_path, profile_enc_path, cipher)
        print("[SUCCESS] Encrypted resume_profile.json → resume_profile.json.enc")
    else:
        print("[NOTE] No resume_profile.json found — run parse-resume first if you want to sync it.")

    print("\nNext steps:")
    if key_was_new:
        print("1. Copy resume_key.txt into GitHub → Settings → Secrets → RESUME_KEY")
        print("2. git add resume.pdf.enc" + (" resume_profile.json.enc" if profile_path.exists() else ""))
        print('3. git commit -m "Add encrypted resume"')
        print("4. git push")
    else:
        print("1. git add resume.pdf.enc" + (" resume_profile.json.enc" if profile_path.exists() else ""))
        print('2. git commit -m "Update encrypted resume"')
        print("3. git push")
    print("\nKeep resume_key.txt local only — it is listed in .gitignore.")


if __name__ == "__main__":
    main()
