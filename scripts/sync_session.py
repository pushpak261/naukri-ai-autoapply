"""
Encrypt local Naukri session cookies for cloud deployment.

Requires an active login session at data/sessions/naukri_session.json.
Log in locally first with: python -m src.naukri_agent.main run --dry-run
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.naukri_agent.utils.secrets import encrypt_file, get_cipher, load_fernet_key


def main() -> None:
    session_file = PROJECT_ROOT / "data" / "sessions" / "naukri_session.json"
    enc_file = PROJECT_ROOT / "session.enc"

    if load_fernet_key(PROJECT_ROOT) is None:
        print("[ERROR] resume_key.txt not found.")
        print("Run python scripts/update_resume.py first to generate a key, or create resume_key.txt manually.")
        sys.exit(1)

    if not session_file.exists():
        print("[ERROR] Active session not found at data/sessions/naukri_session.json")
        print("\nLog in locally first:")
        print("  python -m src.naukri_agent.main run --dry-run")
        print("\nAfter login, stop the bot and run this script again.")
        sys.exit(1)

    cipher = get_cipher(PROJECT_ROOT)
    assert cipher is not None
    encrypt_file(session_file, enc_file, cipher)

    print("[SUCCESS] Encrypted session → session.enc")
    print("\nNext steps:")
    print("1. git add session.enc")
    print('2. git commit -m "Sync Naukri session to cloud"')
    print("3. git push")


if __name__ == "__main__":
    main()
