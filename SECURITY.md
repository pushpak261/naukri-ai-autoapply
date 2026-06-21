# Security & Risk Notes

## Credentials

- Naukri credentials and the Gemini API key are read from `.env` (see
  `.env.example`) or `config.yaml`. **Never commit a filled-in `.env` or
  `config.yaml` with real credentials.** `.gitignore` is configured to
  block `.env`, but double-check before pushing.
- Your password is sent only to `naukri.com` (via Playwright-driven form
  fill) and is never logged. `src/utils/logger.py` includes a `PIIScrubberFilter`
  that redacts emails/phone numbers from log output — review it before
  relying on it for anything beyond casual local logging.
- Session cookies are persisted to `data/sessions/` so you don't have to
  log in on every run. Treat that directory like a credential store — it
  is gitignored, but back it up securely if you back it up at all.

## Automated interaction with Naukri.com — read this before running

This project automates logging in and applying to jobs on Naukri.com,
including a `src/browser/stealth.py` module that patches browser
fingerprinting signals (`navigator.webdriver`, WebGL vendor strings, etc.)
specifically to make the automated browser harder for Naukri's bot
detection to distinguish from a human.

A few things worth knowing before you run this against your real account:

1. **This very likely violates Naukri's Terms of Service.** Most job
   platforms explicitly prohibit automated scraping, automated account
   actions, and bot-driven applications. Anti-bot evasion code makes that
   determination essentially unambiguous, regardless of intent.
2. **Account risk.** Platforms that detect this kind of automation
   typically respond by rate-limiting, shadow-restricting, or permanently
   banning the account — there's usually no appeal process for an
   automation-related ban.
3. **Quality risk to your applications.** Auto-filled screening answers are
   LLM-generated; review `data/logs/` and the `status` command output
   periodically to make sure the agent isn't submitting answers you
   wouldn't want a recruiter to see attributed to you.
4. **This is your own account, your own data, your own risk.** The agent
   doesn't attack third-party systems or access anything you're not
   already authorized to access — but "authorized by you" and "permitted
   by Naukri's ToS" are different things, and only the latter is outside
   this project's (or Claude's) control.

If you'd rather not carry that risk, consider running the agent in
`dry_run: true` mode (scores and logs matches without submitting
anything) or using it purely as a job-matching/triage tool that you act on
manually.

## Reporting issues

This is a personal-use project without a public bug bounty. If you find a
vulnerability in how credentials or session data are handled, fix it
directly or open an issue in your own fork/repo as appropriate.
