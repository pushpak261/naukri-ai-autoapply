import os
from cryptography.fernet import Fernet


def main():
    if not os.path.exists("resume.pdf"):
        print("[ERROR] resume.pdf not found in the current folder.")
        return

    if not os.path.exists("resume_key.txt"):
        print(
            "[ERROR] resume_key.txt not found! You need the original key to update the resume so GitHub can still decrypt it."
        )
        return

    # Read the existing key so we don't have to change GitHub Secrets
    with open("resume_key.txt", "rb") as f:
        key = f.read().strip()

    cipher = Fernet(key)

    # Read the new PDF
    with open("resume.pdf", "rb") as f:
        data = f.read()

    # Encrypt and save
    encrypted_data = cipher.encrypt(data)
    with open("resume.pdf.enc", "wb") as f:
        f.write(encrypted_data)

    # Encrypt and save resume_profile.json if it exists
    profile_path = "resume_profile.json"
    profile_enc_path = "resume_profile.json.enc"
    encrypted_profile_success = False

    if os.path.exists(profile_path):
        with open(profile_path, "rb") as f:
            profile_data = f.read()
        encrypted_profile_data = cipher.encrypt(profile_data)
        with open(profile_enc_path, "wb") as f:
            f.write(encrypted_profile_data)
        encrypted_profile_success = True

    print("[SUCCESS] Your new resume.pdf has been securely encrypted into resume.pdf.enc")
    if encrypted_profile_success:
        print("[SUCCESS] Your resume_profile.json has been securely encrypted into resume_profile.json.enc")
    else:
        print("[NOTE] No resume_profile.json found, skipping profile encryption.")

    print("Next steps:")
    if encrypted_profile_success:
        print("1. git add resume.pdf.enc resume_profile.json.enc")
    else:
        print("1. git add resume.pdf.enc")
    print('2. git commit -m "Update resume and profile"')
    print("3. git push")


if __name__ == "__main__":
    main()
