$ErrorActionPreference = "Stop"

# Single package root - Driver View is the same app with ?view=driver.
$platformRoot = $PSScriptRoot
$venvPath = Join-Path $platformRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$appPort = if ($env:APP_PORT) { $env:APP_PORT } else { "8502" }

if (-not (Test-Path $pythonExe)) {
    Write-Host "Run .\run.ps1 first to create the virtual environment." -ForegroundColor Yellow
    exit 1
}

$driverUrl = "http://127.0.0.1:$appPort/?view=driver"
Write-Host "Starting L and P Driver App at $driverUrl" -ForegroundColor Green
Write-Host "Tip: run .\run-fleet.ps1 to start website + dispatch together." -ForegroundColor Gray

& $pythonExe -m streamlit run (Join-Path $platformRoot "app.py") `
    --server.address 127.0.0.1 `
    --server.port $appPort `
    --server.headless false
