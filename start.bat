@echo off
REM 一键启动 prompt-gen（双击即可）
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
chcp 65001 >nul

if not exist ".venv\Scripts\python.exe" (
  echo [提示] 未找到 .venv，请先在 PowerShell 执行: .\start.ps1
  pause
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo [提示] 已创建 .env，请填入 DEEPSEEK_API_KEY 后重新双击本文件。
    notepad ".env"
    pause
    exit /b 2
  )
)

echo.
echo 启动 prompt-gen 引导菜单...
echo.
".venv\Scripts\prompt-gen.exe" %*
set EXITCODE=%ERRORLEVEL%
echo.
pause
exit /b %EXITCODE%
