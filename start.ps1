# 一键启动 prompt-gen（Windows PowerShell）
# 用法：在项目根目录执行  .\start.ps1
# 或资源管理器中右键「使用 PowerShell 运行」

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:PYTHONIOENCODING = "utf-8"
try { chcp 65001 | Out-Null } catch {}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$venvPromptGen = Join-Path $PSScriptRoot ".venv\Scripts\prompt-gen.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "未找到 .venv，正在创建虚拟环境…" -ForegroundColor Yellow
    $py = "E:\04Programming\CodingEnvironment\Python\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
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

if (Test-Path $venvPromptGen) {
    & $venvPromptGen @args
} else {
    & $venvPython -m prompt_gen @args
}

exit $LASTEXITCODE
