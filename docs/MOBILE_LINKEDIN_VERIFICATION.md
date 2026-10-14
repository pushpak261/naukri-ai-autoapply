# LinkedIn verification from a phone

This flow uses the existing backend's Chromium browser and authenticated HTTP requests. It requires no paid remote-desktop service. One browser runs at a time; agents and application-status sync must be stopped before opening verification.

1. Sign into your dashboard and open **LinkedIn**. Save your LinkedIn email in Authentication first.
2. Select **Verify LinkedIn**. Wait for the live browser image. Tap a field in the image, type its contents into the text box beneath it, then select **Type into focused field**. Repeat for email/password. Use **Clear focused field**, Tab, Backspace, Enter, and scroll buttons as needed. Tap buttons and CAPTCHA images directly in the browser image.
3. Complete LinkedIn verification yourself. This flow does not solve or bypass CAPTCHA. If LinkedIn refuses the cloud browser or cannot load a challenge, close the browser; successful authentication cannot be guaranteed on a datacenter IP.
4. Once you see your LinkedIn feed, select **Save verified session**. The backend checks authenticated profile indicators and a LinkedIn session cookie before saving encrypted state. An unverified browser is not saved.
5. Download the **encrypted session** file to your phone and keep it private. Close verification, then start a **dry run** in Agent Control.

The browser expires after ten minutes. Only the dashboard account that opened it can view or control it. Screens are refreshed roughly every three seconds; allow a moment between taps. Navigation is restricted to LinkedIn and its verification resources.

## Free hosting limits

The existing free Koyeb instance has a temporary disk. Saved sessions, dashboard accounts, and resume data can be lost on sleep, restart, or redeploy. The encrypted phone backup provides a manual recovery option for the LinkedIn session only; it is not automatic database persistence. After a reset, register/login again, save the same LinkedIn email, upload your resume, and restore the session file. The dashboard email and server encryption key must match the backup. Restore does not guarantee that LinkedIn still accepts an expired session or a changed server/IP.

Hosting must keep a stable secret `SESSION_ENCRYPTION_KEY` across deployments. The backend refuses remote verification without it. Both Fernet keys and private passphrases are supported and always encrypt new sessions. Session backups are bound to the dashboard owner and configured LinkedIn email. Do not share the backup, cookies, passwords, or secret key.

Memory is tight on the free instance. Verification blocks agent starts, and verification itself will not start while any agent or status-sync browser is running. This is intended for personal use; it is not a guarantee of unlimited free hosting or reliable operation for multiple concurrent clients.
