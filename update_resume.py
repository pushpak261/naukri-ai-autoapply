import os
from cryptography.fernet import Fernet

def main():
    if not os.path.exists('resume.pdf'):
        print("❌ Error: resume.pdf not found in the current folder.")
        return
        
    if not os.path.exists('resume_key.txt'):
        print("❌ Error: resume_key.txt not found! You need the original key to update the resume so GitHub can still decrypt it.")
        return

    # Read the existing key so we don't have to change GitHub Secrets
    with open('resume_key.txt', 'rb') as f:
        key = f.read().strip()
        
    cipher = Fernet(key)
    
    # Read the new PDF
    with open('resume.pdf', 'rb') as f:
        data = f.read()
        
    # Encrypt and save
    encrypted_data = cipher.encrypt(data)
    with open('resume.pdf.enc', 'wb') as f:
        f.write(encrypted_data)
        
    print("✅ Success! Your new resume.pdf has been securely encrypted into resume.pdf.enc")
    print("Next steps:")
    print("1. git add resume.pdf.enc")
    print("2. git commit -m \"Update resume\"")
    print("3. git push")

if __name__ == "__main__":
    main()
