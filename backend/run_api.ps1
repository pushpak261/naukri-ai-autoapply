# Start the FastAPI dashboard API (run from backend/ or repo root).
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot
python -m uvicorn backend.main:app `
    --reload `
    --host 127.0.0.1 `
    --port 8000 `
    --loop backend.loop:create_event_loop
