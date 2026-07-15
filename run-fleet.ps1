$ErrorActionPreference = "Stop"

# ============================================================
# L & P Fleet Stack - one command for Website + Dispatch + Driver
# Usage:  .\run-fleet.ps1
# ============================================================

$repoRoot = $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$venvPath = Join-Path $repoRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$logDir = Join-Path $repoRoot "deploy"
$dispatchLog = Join-Path $logDir "fleet-dispatch.log"
$dispatchErr = Join-Path $logDir "fleet-dispatch.err"

$webPort = if ($env:WEB_PORT) { $env:WEB_PORT } else { "8080" }
$appPort = if ($env:APP_PORT) { $env:APP_PORT } else { "8502" }

function Stop-PortListeners {
    param([int[]]$Ports)
    foreach ($port in $Ports) {
        try {
            $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
            foreach ($conn in $listeners) {
                if ($conn.OwningProcess -and $conn.OwningProcess -gt 0) {
                    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
                }
            }
        } catch { }
    }
}

function Wait-HttpOk {
    param([string]$Url, [int]$Seconds = 45)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return $true }
        } catch { }
        Start-Sleep -Seconds 1
    }
    return $false
}

# --- venv ---
if (-not (Test-Path $pythonExe)) {
    Write-Host "No .venv found. Creating with .\run.ps1 (this may take a few minutes)..." -ForegroundColor Yellow
    & (Join-Path $repoRoot "run.ps1")
    if (-not (Test-Path $pythonExe)) {
        Write-Host "ERROR: Still no .venv. Install Python 3.11+ and re-run." -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

Write-Host ""
Write-Host "=== L & P Fleet Stack ===" -ForegroundColor Cyan
Write-Host "Repo: $repoRoot"
Write-Host "Freeing ports $webPort and $appPort ..." -ForegroundColor Gray
Stop-PortListeners -Ports @([int]$webPort, [int]$appPort)
Start-Sleep -Seconds 1

$env:LP_APP_URL = "http://127.0.0.1:$appPort"
$env:LP_WEB_MODE = "0"

# --- Dispatch (Streamlit) in background with logs ---
$appPy = Join-Path $repoRoot "app.py"
Write-Host "Starting DISPATCH on http://127.0.0.1:$appPort ..." -ForegroundColor Green

# Use WorkingDirectory so paths with spaces (&) work reliably
$dispatchProc = Start-Process -FilePath $pythonExe `
    -WorkingDirectory $repoRoot `
    -ArgumentList @(
        "-m", "streamlit", "run", "app.py",
        "--server.address", "127.0.0.1",
        "--server.port", $appPort,
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false"
    ) `
    -RedirectStandardOutput $dispatchLog `
    -RedirectStandardError $dispatchErr `
    -PassThru `
    -WindowStyle Hidden

Write-Host "  Dispatch PID: $($dispatchProc.Id)  (logs: deploy\fleet-dispatch.*)" -ForegroundColor Gray

$healthUrl = "http://127.0.0.1:$appPort/_stcore/health"
if (-not (Wait-HttpOk -Url $healthUrl -Seconds 50)) {
    Write-Host ""
    Write-Host "ERROR: Dispatch did not become healthy on port $appPort." -ForegroundColor Red
    Write-Host "Last error log:" -ForegroundColor Yellow
    if (Test-Path $dispatchErr) { Get-Content $dispatchErr -Tail 30 | ForEach-Object { Write-Host "  $_" } }
    if (Test-Path $dispatchLog) { Get-Content $dispatchLog -Tail 15 | ForEach-Object { Write-Host "  $_" } }
    Write-Host ""
    Write-Host "Try dispatch alone in the foreground to see errors:" -ForegroundColor Yellow
    Write-Host "  .\run.ps1" -ForegroundColor White
    exit 1
}

Write-Host "  Dispatch healthy." -ForegroundColor Green

# Probe home page (catches import crashes after health)
try {
    $home = Invoke-WebRequest -Uri "http://127.0.0.1:$appPort/" -UseBasicParsing -TimeoutSec 15
    if ($home.StatusCode -ne 200) { throw "HTTP $($home.StatusCode)" }
    Write-Host "  Dispatch UI responding." -ForegroundColor Green
} catch {
    Write-Host "  WARNING: health OK but home page failed: $_" -ForegroundColor Yellow
}

# --- Open browser hub ---
$websiteUrl = "http://127.0.0.1:$webPort/"
$dispatchUrl = "http://127.0.0.1:$appPort/"
$driverUrl = "http://127.0.0.1:$appPort/?view=driver"

Write-Host ""
Write-Host "Fleet URLs (bookmark these):" -ForegroundColor Cyan
Write-Host "  Website:   $websiteUrl" -ForegroundColor Yellow
Write-Host "  Dispatch:  $dispatchUrl" -ForegroundColor Yellow
Write-Host "  Driver:    $driverUrl" -ForegroundColor Yellow
Write-Host ""

# Open Dispatch first (main app), then website hub
Start-Process $dispatchUrl
Start-Sleep -Milliseconds 500
Start-Process $websiteUrl

Write-Host "Starting WEBSITE on $websiteUrl ..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the website. Dispatch keeps running in the background." -ForegroundColor Gray
Write-Host "To stop Dispatch later:  Get-NetTCPConnection -LocalPort $appPort -State Listen | % { Stop-Process -Id `$_.OwningProcess -Force }" -ForegroundColor DarkGray
Write-Host ""

Set-Location -LiteralPath (Join-Path $repoRoot "web")
& $pythonExe -m http.server $webPort --bind 127.0.0.1
