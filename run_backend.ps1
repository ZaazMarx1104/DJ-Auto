# Run the DJ-Auto backend. Use this from the project root (DJ-Auto).
# Requires: .venv already created (py -3.12 -m venv .venv) and deps installed (pip install -r requirements.txt).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Missing .venv. Create it with: py -3.12 -m venv .venv"
    exit 1
}

# Use the venv's Python so the process (and reloader subprocess) see the venv's packages (e.g. jiter).
& $venvPython -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
