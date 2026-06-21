# 🤖 Naukri.com AI Job Application Agent

A production-grade, AI-powered agent that automatically discovers and applies to relevant jobs on Naukri.com based on your resume, preferences, and intelligent matching.

## ✨ Features

- **🧠 AI-Powered Matching** — Uses Google Gemini to analyze job descriptions against your resume and compute a match score (0-100) with detailed reasoning
- **🌐 Browser Automation** — Playwright-based automation with anti-detection stealth patches and human-like interaction patterns
- **📄 Smart Resume Parsing** — Extracts and structures your PDF resume into skills, experience, education, and achievements
- **💬 Auto Question Answering** — AI fills screening questionnaires (CTC, notice period, experience) during the apply flow
- **🛡️ Safety Controls** — Daily application caps, match score thresholds, exclusion filters, and dry-run mode
- **📊 Rich Dashboard** — Beautiful terminal output with progress indicators, match scores, and run statistics
- **💾 Persistent State** — SQLite database tracks all applied jobs, scores, and run history
- **🔐 Supervised Mode** — Visible browser with manual OTP handling for security

## 📋 Prerequisites

- Python 3.11 or higher
- Google Gemini API key ([Get one here](https://ai.google.dev/))
- A Naukri.com account
- Your resume as a PDF file

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd "AI Agent Naukri"
pip install -r requirements.txt
playwright install chromium

# Optional, for contributing / running lint+type checks locally:
pip install -r requirements-dev.txt
pre-commit install
```

### 2. Initialize Configuration

```bash
python -m src.main init
```

This creates a `.env` file from the template. Edit it with your credentials:

```env
NAUKRI_EMAIL=your_email@example.com
NAUKRI_PASSWORD=your_password
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Configure Job Preferences

Edit `config.yaml` to set:

- **Search keywords** — Job titles you're looking for
- **Locations** — Preferred cities or "Remote"
- **Experience range** — Min/max years
- **Profile details** — CTC, notice period (for auto-filling forms)
- **Application controls** — Daily cap, match threshold
- **Exclusions** — Companies or keywords to skip

### 4. Run the Agent

```bash
# Dry run first (scores jobs but doesn't apply)
python -m src.main run --dry-run

# Full run (actually applies)
python -m src.main run

# With overrides
python -m src.main run --cap 10 --threshold 80
```

### 5. View Statistics

```bash
python -m src.main status
```

## 🎯 CLI Commands

| Command | Description |
|---------|-------------|
| `python -m src.main run` | Start the application agent |
| `python -m src.main run --dry-run` | Score jobs without applying |
| `python -m src.main status` | View application statistics |
| `python -m src.main parse-resume <path>` | Test resume parsing |
| `python -m src.main test-match <url>` | Test matching against a job |
| `python -m src.main init` | Initialize config files |

## 🏗️ Architecture

```
src/
├── config/          # Settings, constants, selectors
├── ai/              # Gemini-powered resume parsing, job matching, Q&A
├── browser/         # Playwright engine, stealth, login, search, apply
├── database/        # SQLite models and repository
├── orchestrator/    # Main agent loop
├── utils/           # Logger, helpers
└── main.py          # CLI entry point
```

### How It Works

1. **Parse Resume** → Extracts your PDF and creates a structured profile via Gemini AI
2. **Login** → Restores saved session or performs fresh login (with OTP support)
3. **Search** → Searches Naukri across all keyword × location combinations
4. **Score** → Each job is scored 0-100 by Gemini against your resume
5. **Apply** → Jobs above the threshold are auto-applied with AI-filled screening questions
6. **Log** → Every action is recorded in SQLite for tracking and analytics

## ⚙️ Configuration Reference

See `config.yaml` for the full list of configurable options. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `application.daily_cap` | 25 | Max applications per day |
| `application.match_score_threshold` | 70 | Minimum score to auto-apply |
| `application.delay_between_applies_min` | 30s | Min delay between apps |
| `application.delay_between_applies_max` | 90s | Max delay between apps |
| `application.skip_external_apply` | true | Skip external redirects |
| `search.max_pages` | 3 | Pages to scan per keyword |
| `search.freshness` | 7 | Job age in days |

## 🛡️ Safety & Ethics

- **Supervised use only** — The browser is visible; you must be present for OTP
- **Rate limited** — Configurable delays prevent rapid-fire applications
- **Daily caps** — Hard limit on applications per day
- **Dry-run mode** — Test everything without actually applying
- **Terms of Service** — This automates account actions on Naukri.com using
  anti-bot-detection patches, which very likely violates Naukri's Terms of
  Service and carries real account-ban risk. Read **[SECURITY.md](SECURITY.md)**
  before running this against a real account.

## 🧪 Development & Testing

```bash
# Run the test suite
pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Lint
ruff check .

# Format
black .

# Type-check
mypy src/
```

CI (`.github/workflows/ci.yml`) runs all of the above on every push/PR.
`.pre-commit-config.yaml` runs ruff + black automatically before each commit
once you've run `pre-commit install`.

## 📂 Data Storage

All data is stored locally in the `data/` directory:

- `data/naukri_agent.db` — SQLite database with all jobs, applications, and stats
- `data/sessions/` — Browser session state for login persistence
- `data/logs/` — Daily log files

## ☁️ Cloud Deployment (GitHub Actions)

This project is fully configured to run automatically and completely for free using **GitHub Actions**.

1. Navigate to your repository on GitHub.
2. Go to **Settings** > **Secrets and variables** > **Actions**.
3. Click **New repository secret** and add the following 3 secrets:
   - `GEMINI_API_KEY`: Your Gemini API key.
   - `NAUKRI_EMAIL`: Your Naukri account email.
   - `NAUKRI_PASSWORD`: Your Naukri password.

By default, the GitHub Actions workflow (`.github/workflows/auto-apply.yml`) is scheduled to run daily at `30 2 * * *` UTC (8:00 AM IST) on an Ubuntu runner.
*Note: Since GitHub Actions runners are ephemeral, any state tracked in the local SQLite DB will be lost between runs unless you configure an external database.*

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| Login fails | Check credentials in `.env`, ensure no CAPTCHA |
| OTP timeout | Enter OTP faster in the browser window (120s limit) |
| Apply button not found | Naukri may have updated their UI; update selectors in `constants.py` |
| Low match scores | Adjust `match_score_threshold` or refine resume |
| Bot detected | Increase delays, reduce daily cap, use a VPN |

## 📜 License

This project is for personal, educational use only. Use responsibly.
