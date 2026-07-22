@echo off
REM Real launcher for Windows.
REM Derives project root via %~dp0, auto-initializes venv on first run, then silently installs the global command.
setlocal
for %%I in ("%~dp0..") do set "PG_HOME=%%~fI"
if defined PROMPT_GEN_HOME set "PG_HOME=%PROMPT_GEN_HOME%"
set "PG_VENV=%PG_HOME%\.venv"
set "PY=python"
where python >nul 2>&1 || set "PY=py"

REM Skip init if venv exists and prompt_gen is importable.
if exist "%PG_VENV%\Scripts\python.exe" (
    "%PG_VENV%\Scripts\python.exe" -c "import prompt_gen" >nul 2>&1 && goto :run
)

echo [prompt-gen] First run: creating virtual environment...
"%PY%" -m venv "%PG_VENV%"
"%PG_VENV%\Scripts\python.exe" -m pip install -U pip
"%PG_VENV%\Scripts\python.exe" -m pip install -e "%PG_HOME%[dev]"
if not exist "%PG_HOME%\.env" (if exist "%PG_HOME%\.env.example" copy "%PG_HOME%\.env.example" "%PG_HOME%\.env" >nul)

:run
rem Install the global command on first run (idempotent, silent).
"%PG_VENV%\Scripts\python.exe" "%PG_HOME%\install.py" >nul 2>&1

cd /d "%PG_HOME%"
"%PG_VENV%\Scripts\python.exe" -m prompt_gen %*
