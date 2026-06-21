import os
import json
from pathlib import Path
from cryptography.fernet import Fernet

def main():
    session_file = Path('data/sessions/naukri_session.json')
    key_file = Path('resume_key.txt')
    enc_file = Path('session.enc')

    if not key_file.exists():
        print("❌ Error: resume_key.txt not found. You need this key to encrypt your session.")
        return

    if not session_file.exists():
        print("❌ Error: Active session not found at data/sessions/naukri_session.json")
        print("\nYou need to log in locally first so we can grab your cookies!")
        print("Run this command to open the browser and log in:")
        print("  python -m src.main run --dry-run")
        print("\nOnce you successfully log in and the bot starts searching, you can stop it.")
        print("Then run `python sync_session.py` again.")
        return

    # Read the existing key
    with open(key_file, 'rb') as f:
        key = f.read().strip()
        
    cipher = Fernet(key)
    
    # Read the session JSON
    with open(session_file, 'rb') as f:
        data = f.read()
        
    # Encrypt and save
    encrypted_data = cipher.encrypt(data)
    with open(enc_file, 'wb') as f:
        f.write(encrypted_data)
        
    print("✅ Success! Your session cookies have been securely encrypted into session.enc")
    print("Next steps to push this to your cloud bot:")
    print("1. git add session.enc")
    print("2. git commit -m \"Sync session cookies to cloud\"")
    print("3. git push")

if __name__ == "__main__":
    main()
