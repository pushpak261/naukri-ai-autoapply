# Session Cookie Syncing Plan

Naukri's security system is enforcing an OTP because GitHub Actions runs on cloud data center IP addresses (Azure). Naukri flags these IPs as suspicious 100% of the time, and there is no way to turn off Naukri's server-side security checks.

However, we can completely **bypass the login screen and the OTP** by using "Session Cookies". If you log in once on your local laptop, we can encrypt your browser session cookies and send them to the cloud. The cloud bot will then use those cookies to be instantly recognized as you, without ever needing an email, password, or OTP!

## Proposed Changes

### 1. Create a `sync_session.py` Script
I will write a local helper script for you. When you run it:
- It will open a visible Chromium browser on your laptop.
- You will log in to Naukri manually just one time.
- It will save your session cookies.
- It will use your existing `resume_key.txt` to securely encrypt your session into a `session.enc` file.

### 2. Update Cloud Workflow
I will update your `.github/workflows/auto-apply.yml` to:
- Decrypt `session.enc` back into `data/sessions/naukri_session.json` right before the bot starts.
- Because of this, the cloud bot will skip the login screen entirely and jump straight into applying for jobs.

## User Review Required
> [!WARNING]
> Please never share your passwords in the chat! It's always best to keep them private in your `.env` file or GitHub Secrets.

> [!IMPORTANT]
> Do you approve of this "Session Cookie" approach? It is the only reliable way to bypass OTPs in a cloud environment without building a complex email-reading bot.
