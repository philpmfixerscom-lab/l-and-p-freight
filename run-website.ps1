$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPath = Join-Path $PSScriptRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "No .venv found. Run .\run.ps1 first to set up Python." -ForegroundColor Red
    exit 1
}

$webPort = if ($env:WEB_PORT) { $env:WEB_PORT } else { "8080" }
$appPort = if ($env:APP_PORT) { $env:APP_PORT } else { "8502" }

$ErrorActionPreference = "Continue"
Get-NetTCPConnection -LocalPort $webPort,$appPort -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
$ErrorActionPreference = "Stop"

$env:LP_APP_URL = "http://127.0.0.1:$appPort"

Write-Host "Starting dispatch app on http://127.0.0.1:$appPort ..." -ForegroundColor Cyan
Start-Process -FilePath $pythonExe -ArgumentList @(
    "-m", "streamlit", "run", "app.py",
    "--server.address", "127.0.0.1",
    "--server.port", $appPort,
    "--server.headless", "true"
) -WindowStyle Hidden

Write-Host "Starting marketing website on http://127.0.0.1:$webPort ..." -ForegroundColor Green
Write-Host "  Landing page: http://127.0.0.1:$webPort" -ForegroundColor Yellow
Write-Host "  Dispatch app: http://127.0.0.1:$appPort" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop the website server (app keeps running until you close it)." -ForegroundColor Gray

Set-Location -LiteralPath (Join-Path $PSScriptRoot "web")
& $pythonExe -m http.server $webPort --bind 127.0.0.1