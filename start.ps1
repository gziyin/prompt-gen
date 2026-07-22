# 一键启动 prompt-gen（Windows PowerShell）
# 用法：在项目根目录执行  .\start.ps1
# 或资源管理器中右键「使用 PowerShell 运行」
# 首次运行会自动创建 .venv 并安装全局命令 `prompt-gen`。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:PYTHONIOENCODING = "utf-8"
try { chcp 65001 | Out-Null } catch {}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "未找到 .venv，正在创建虚拟环境…" -ForegroundColor Yellow
    $py = "python"
    if (-not (Get-Command $py -ErrorAction SilentlyContinue)) { $py = "py" }
    & $py -m venv .venv
    & $venvPython -m pip install -U pip
    & $venvPython -m pip install -e ".[dev]"
}

if (-not (Test-Path (Join-Path $PSScriptRoot ".env"))) {
    if (Test-Path (Join-Path $PSScriptRoot ".env.example")) {
        Copy-Item (Join-Path $PSScriptRoot ".env.example") (Join-Path $PSScriptRoot ".env")
        Write-Host "已创建 .env（来自 .env.example）。请先编辑填入 DEEPSEEK_API_KEY。" -ForegroundColor Yellow
        Write-Host "记事本打开: notepad .env" -ForegroundColor Yellow
        notepad (Join-Path $PSScriptRoot ".env")
        Write-Host "保存 .env 后，按回车继续…" -ForegroundColor Cyan
        Read-Host | Out-Null
    }
}

Write-Host ""
Write-Host "启动 prompt-gen 引导菜单…" -ForegroundColor Green
Write-Host ""

# 交由 bin\prompt-gen.cmd：自动安装全局命令并启动
& "$PSScriptRoot\bin\prompt-gen.cmd" @args
exit $LASTEXITCODE
