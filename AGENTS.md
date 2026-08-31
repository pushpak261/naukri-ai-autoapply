# AI Agent Naukri - Production Configuration

## Koyeb Deployment Configuration

### Environment Variables Required on Koyeb

Set these environment variables in your Koyeb deployment configuration:

| Variable | Value | Description |
|---|---|---|
| `HEADLESS` | `true` | Force headless browser mode (required for headless servers) |
| `SESSION_ENCRYPTION_KEY` | `<random-string>` | Session encryption key (e.g., `my-koyeb-secret-key-2024`) |
| `NAUKRI_EMAIL` | `<your-email>` | Naukri account email |
| `NAUKRI_PASSWORD` | `<your-password>` | Naukri account password |
| `LINKEDIN_EMAIL` | `<your-email>` | LinkedIn account email (optional) |
| `LINKEDIN_PASSWORD` | `<your-password>` | LinkedIn account password (optional) |
| `GEMINI_API_KEY` | `<your-api-key>` | Gemini API key for AI matching (optional) |
| `DASHBOARD_API_KEY` | `<random-string>` | Optional API key for securing the dashboard |

### Docker Deployment

The application now uses Docker deployment instead of buildpack:

1. Push changes to git - Koyeb will auto-redeploy using Docker
2. The Dockerfile serves the API with uvicorn on port 8000
3. Playwright/Chromium is pre-installed in the Docker image

### Configuration Files

- `config.yaml` - Naukri agent configuration (now included in git)
- `linkedin_config.yaml` - LinkedIn agent configuration (now included in git)
- Both files use environment variable placeholders (e.g., `${NAUKRI_EMAIL:-}`)

### Resume File

- Resume PDF should be placed at `data/resumes/pushpak_pandharpatte_9921626877.pdf`
- This path is now included in the Docker image

### Code Changes Made

1. **Browser Engine Auto-Detection** - Both Naukri and LinkedIn browser engines now:
   - Auto-detect production environment (no DISPLAY + not Windows)
   - Force headless mode in production regardless of HEADLESS env var
   - Retry with headless mode if headed launch fails

2. **Environment Variable Injection** - Agent subprocesses now:
   - Automatically set `HEADLESS=true` when running on headless servers
   - Applied in `multi_agent.py`, `agent.py`, and `agent_runtime.py`

3. **Config Files in Git** - Configuration files are now:
   - Removed from `.gitignore` 
   - Use environment variable placeholders for credentials
   - Included in Docker image

4. **Dockerfile Updates** - Dockerfile now:
   - Serves the API with uvicorn instead of CLI agent
   - Sets `HEADLESS=true` as default environment variable
   - Copies config files and resume into the image
   - Added performance optimizations (workers, concurrency limits, Python optimizations)

5. **Dockerignore Updates** - `.dockerignore` now:
   - Allows `data/resumes/` to include resume PDF
   - Allows `config.yaml` and `linkedin_config.yaml`
   - Excludes sensitive runtime artifacts (sessions, logs, databases)

6. **Performance Optimizations** (Latest Update):
   - **Backend Startup**: Deferred account resolution to first request (faster cold starts)
   - **API Caching**: Enabled 30s cache for GET requests (reduces duplicate API calls)
   - **Frontend Timeouts**: Increased API timeout from 12s to 30s (handles cold starts better)
   - **Dashboard Polling**: Reduced refetch intervals (stats: 60s, session: 60s, metrics: 120s)
   - **Health Check**: Increased health check timeout from 5s to 15s
   - **Build Optimization**: Enhanced Vite config with better chunk splitting and minification
   - **Database Queries**: Parallel execution of independent queries in stats endpoint
   - **Uvicorn Config**: Added concurrency limits and keep-alive timeout for better performance

### Verification Steps

After deployment:

1. Check `/api/health` returns 200
2. Start agents via Command Center
3. Check `/api/multi/output?platform=naukri` for logs
4. Verify browser launches in headless mode (no display crash)
5. Monitor Koyeb logs for OOM kills or crash messages
6. Test dashboard load time - should load within 5-10 seconds on cold start

### Performance Monitoring

- Dashboard should load within 5-10 seconds on cold start
- Subsequent page loads should be <2 seconds with caching
- API response times should be <500ms for cached endpoints
- Monitor Koyeb logs for memory usage and startup times

### Resource Constraints

- Free tier: 0.1 vCPU, 512MB RAM
- Playwright/Chromium may be borderline on 512MB
- Consider upgrading to Starter plan if experiencing OOM kills

### Persistence

- SQLite database is ephemeral on Koyeb free tier
- Data is lost on every redeploy/restart
- Consider upgrading to a plan with persistent storage if data persistence is required
