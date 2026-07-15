$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$platformRoot = Join-Path $repoRoot "lawson-freight-platform"
$venvPath = Join-Path $repoRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "No virtual environment found. Running setup via .\run.ps1 ..." -ForegroundColor Yellow
    & (Join-Path $repoRoot "run.ps1")
    exit $LASTEXITCODE
}

$webPort = if ($env:WEB_PORT) { $env:WEB_PORT } else { "8080" }
$appPort = if ($env:APP_PORT) { $env:APP_PORT } else { "8502" }

$ErrorActionPreference = "Continue"
Get-NetTCPConnection -LocalPort $webPort, $appPort -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
$ErrorActionPreference = "Stop"

$env:LP_APP_URL = "http://127.0.0.1:$appPort"
$env:LP_WEB_MODE = "0"

Write-Host "=== L & P Fleet Stack ===" -ForegroundColor Cyan
Write-Host "Starting dispatch app on http://127.0.0.1:$appPort ..." -ForegroundColor Green
Start-Process -FilePath $pythonExe -ArgumentList @(
    "-m", "streamlit", "run", (Join-Path $platformRoot "app.py"),
    "--server.address", "127.0.0.1",
    "--server.port", $appPort,
    "--server.headless", "true"
) -WindowStyle Hidden

Start-Sleep -Seconds 5

try {
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:$appPort/_stcore/health" -UseBasicParsing -TimeoutSec 20
    if ($health.StatusCode -eq 200) {
        Write-Host "Dispatch app healthy" -ForegroundColor Green
    }
} catch {
    Write-Host "Dispatch app still starting — refresh browser in a few seconds." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Fleet URLs:" -ForegroundColor Cyan
Write-Host "  Website:      http://127.0.0.1:$webPort" -ForegroundColor Yellow
Write-Host "  Dispatch:     http://127.0.0.1:$appPort" -ForegroundColor Yellow
Write-Host "  Driver App:   http://127.0.0.1:$appPort/?view=driver" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop the website server (dispatch keeps running)." -ForegroundColor Gray

Set-Location -LiteralPath (Join-Path $platformRoot "web")
& $pythonExe -m http.server $webPort --bind 127.0.0.1