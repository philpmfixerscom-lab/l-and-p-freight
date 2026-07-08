$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPath = Join-Path $PSScriptRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "Run .\run.ps1 first to create the virtual environment." -ForegroundColor Yellow
    exit 1
}

$driverUrl = "http://127.0.0.1:8503?view=driver"
Write-Host "Starting L and P Driver App at $driverUrl" -ForegroundColor Green
& $pythonExe -m streamlit run (Join-Path $PSScriptRoot "app.py") `
    --server.address 127.0.0.1 `
    --server.port 8503 `
    --server.headless false