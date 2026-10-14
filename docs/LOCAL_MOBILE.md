# Free local agent with mobile control

Install Python 3.11+ and Node.js 22 LTS on your Windows computer. Download this repository (or pull the latest main), extract it, and double-click `start-local.cmd`. The first run installs dependencies and Chromium and builds the dashboard. Keep the launcher window open.

1. Register a new account in the local dashboard opened on your computer. Cloud accounts and data are separate; cloud data is not downloaded automatically.
2. Upload your resume. On the LinkedIn page, save your LinkedIn email. A saved LinkedIn password is optional in local mode.
3. Keep **Dry Run** enabled and start the LinkedIn agent in Agent Control. A browser opens on the computer. Sign in there and complete LinkedIn verification manually within five minutes. The agent saves the verified session encrypted on the computer and reuses it on later runs. LinkedIn can request verification again.
4. Put your phone on the same private Wi-Fi. Open the **Phone dashboard** URL printed by the launcher, register/login with your local dashboard account, and use Agent Control to start, stop, and monitor runs. Use this local URL, not the Vercel deployment. Verification is completed on the computer, not on the phone.

Allow Windows Firewall access for **Private networks only** if prompted. Turn off VPN/client isolation if it prevents devices communicating on your own Wi-Fi. Local HTTP is intended only for your trusted private network; do not expose or forward port 8005 to the internet. The computer must stay awake while jobs run.

Local settings, databases, resumes, and encrypted sessions live in `local-workspace/`, which is excluded from Git. Keep this folder when updating code; back it up privately. Deleting it removes local accounts and session keys. Existing settings and dry-run choices are preserved between launches. Dry-run does not submit applications; only turn it off when you intend to submit real applications.

For Linux/macOS, install requirements and Chromium, build `frontend` with `VITE_API_BASE_URL='' VERCEL=1 npm run build`, and run `python scripts/local_dashboard.py` from a desktop session. A visible graphical display is required.
