# Start the FastAPI dashboard API (run from backend/ or repo root).
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot
python -m backend
