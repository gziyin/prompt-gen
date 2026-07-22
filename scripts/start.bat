@echo off
REM One-click launcher for prompt-gen (double-click to run).
REM This script lives in <repo>/scripts; the project root is its parent.
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
chcp 65001 >nul

if not exist ".venv\Scripts\python.exe" (
  echo [hint] .venv not found. Run scripts\start.ps1 or, in Git Bash, run: bash scripts/start.sh
  pause
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo [hint] Created .env. Please fill in DEEPSEEK_API_KEY, then double-click this file again.
    notepad ".env"
    pause
    exit /b 2
  )
)

echo.
echo Starting prompt-gen...
echo.

REM Delegate to bin\prompt-gen.cmd: installs the global command and launches.
call "%~dp0..\bin\prompt-gen.cmd" %*
set EXITCODE=%ERRORLEVEL%
echo.
pause
exit /b %EXITCODE%
