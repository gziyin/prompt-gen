# One-click launcher for prompt-gen (Windows PowerShell).
# Usage: from the project root run  .\scripts\start.ps1
#        or right-click in Explorer and "Run with PowerShell"
# On first run it creates .venv and installs the global `prompt-gen` command.

$ErrorActionPreference = "Stop"

# This script lives in <repo>/scripts; the project root is its parent.
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

$env:PYTHONIOENCODING = "utf-8"
try { chcp 65001 | Out-Null } catch {}

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "No .venv found, creating virtual environment..." -ForegroundColor Yellow
    $py = "python"
    if (-not (Get-Command $py -ErrorAction SilentlyContinue)) { $py = "py" }
    & $py -m venv .venv
    & $venvPython -m pip install -U pip
    & $venvPython -m pip install -e ".[dev]"
}

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    if (Test-Path (Join-Path $ProjectRoot ".env.example")) {
        Copy-Item (Join-Path $ProjectRoot ".env.example") (Join-Path $ProjectRoot ".env")
        Write-Host "Created .env from .env.example. Please edit it and set DEEPSEEK_API_KEY." -ForegroundColor Yellow
        Write-Host "Open it with: notepad .env" -ForegroundColor Yellow
        notepad (Join-Path $ProjectRoot ".env")
        Write-Host "After saving .env, press Enter to continue..." -ForegroundColor Cyan
        Read-Host | Out-Null
    }
}

Write-Host ""
Write-Host "Starting prompt-gen..." -ForegroundColor Green
Write-Host ""

# Delegate to bin\prompt-gen.cmd: installs the global command and launches.
& "$ProjectRoot\bin\prompt-gen.cmd" @args
exit $LASTEXITCODE
