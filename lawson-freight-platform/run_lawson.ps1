$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

$venvPath = Join-Path $PSScriptRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$appPy = Join-Path $PSScriptRoot "lawson-freight-platform\app.py"
$reqPath = Join-Path $PSScriptRoot "lawson-freight-platform\requirements.txt"

if (-not (Test-Path $pythonExe)) {
    Write-Host "No .venv found. Run run.ps1 first to set up Python." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $PSScriptRoot "lp_dispatch.db"))) {
    Write-Host "lp_dispatch.db not found. Run run.ps1 once to initialize the shared database." -ForegroundColor Yellow
}

Write-Host "Installing Lawson platform dependencies..." -ForegroundColor Cyan
& $pythonExe -m pip install -r $reqPath -q

$ErrorActionPreference = "Continue"
Get-NetTCPConnection -LocalPort 8503 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
$ErrorActionPreference = "Stop"

$appUrl = "http://127.0.0.1:8503"
Write-Host "Starting Lawson Freight Platform (merged) at $appUrl" -ForegroundColor Green
Write-Host "Standalone Lawson build — run.ps1 on port 8502 is the combined platform (Lawson tabs + Day/Night theme)." -ForegroundColor Yellow
& $pythonExe -m streamlit run $appPy --server.address 127.0.0.1 --server.port 8503 --server.headless false