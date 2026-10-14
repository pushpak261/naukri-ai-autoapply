$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Run-Checked($Program, $Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed. See the error above." }
}
try {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.11 or newer from python.org (include the Python launcher), then run again.' }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 LTS from nodejs.org, then run again.' }
    Run-Checked 'py' @('-3', '-c', 'import sys; assert sys.version_info >= (3,11), "Python 3.11 or newer is required"')
    if (-not (Test-Path '.venv\Scripts\python.exe')) { Run-Checked 'py' @('-3', '-m', 'venv', '.venv') }
    $Python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
    $RequirementsHash = (Get-FileHash 'requirements.txt').Hash
    $Marker = '.venv\local-requirements.txt'
    if (-not (Test-Path $Marker) -or (Get-Content $Marker -Raw).Trim() -ne $RequirementsHash) {
        Run-Checked $Python @('-m', 'pip', 'install', '-r', 'requirements.txt')
        Run-Checked $Python @('-m', 'playwright', 'install', 'chromium')
        Set-Content $Marker $RequirementsHash
    }
    Push-Location frontend
    try {
        $env:VITE_API_BASE_URL = ''
        $env:VERCEL = '1' # Build all requests relative to this local server.
        if (-not (Test-Path 'node_modules')) { Run-Checked 'npm.cmd' @('ci') }
        Run-Checked 'npm.cmd' @('run', 'build')
    } finally { Pop-Location }
    Run-Checked $Python @('scripts/local_dashboard.py')
} catch {
    Write-Host $_ -ForegroundColor Red
    exit 1
}
