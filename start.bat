@echo off
REM One-click launcher for prompt-gen (double-click to run).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
chcp 65001 >nul

if not exist ".venv\Scripts\python.exe" (
  echo [hint] .venv not found. Run .\start.ps1 or, in Git Bash, run: bash start.sh
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
call "%~dp0bin\prompt-gen.cmd" %*
set EXITCODE=%ERRORLEVEL%
echo.
pause
exit /b %EXITCODE%
