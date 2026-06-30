"""
Decrypt resume, profile, and session files for local development.

Reads the key from resume_key.txt or the RESUME_KEY environment variable.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python scripts/decrypt_secrets.py` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from src.naukri_agent.utils.secrets import decrypt_local_secrets, load_fernet_key


def main() -> None:
    if load_fernet_key(PROJECT_ROOT) is None:
        print("[ERROR] No decryption key found.")
        print("  • Place your key in resume_key.txt, or")
        print("  • Set the RESUME_KEY environment variable (same value as the GitHub secret).")
        sys.exit(1)

    messages = decrypt_local_secrets(PROJECT_ROOT)
    if not messages:
        print("[NOTE] No encrypted files found (resume.pdf.enc, resume_profile.json.enc, session.enc).")
        sys.exit(0)

    for message in messages:
        prefix = "[ERROR]" if "Could not decrypt" in message else "[OK]"
        print(f"{prefix} {message}")

    if any("Could not decrypt" in message for message in messages):
        sys.exit(1)

    print("\nNext step: python -m src.naukri_agent.main run --dry-run")


if __name__ == "__main__":
    main()
