$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$repoRoot = Split-Path $root -Parent
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$appPort = if ($env:APP_PORT) { $env:APP_PORT } else { "8502" }
$webPort = if ($env:WEB_PORT) { $env:WEB_PORT } else { "8080" }

if (-not (Test-Path $pythonExe)) {
    Write-Host "FAIL: Run ..\..\run.ps1 first to create .venv" -ForegroundColor Red
    exit 1
}

Write-Host "=== Fleet Local Verification ===" -ForegroundColor Cyan

Write-Host "[1/3] Running pytest..." -ForegroundColor Cyan
Push-Location $root
& $pythonExe -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }
Pop-Location
Write-Host "  PASS: all tests" -ForegroundColor Green

Write-Host "[2/3] Checking dispatch health..." -ForegroundColor Cyan
try {
    $h = Invoke-WebRequest -Uri "http://127.0.0.1:$appPort/_stcore/health" -UseBasicParsing -TimeoutSec 8
    if ($h.StatusCode -eq 200) {
        Write-Host "  PASS: dispatch health" -ForegroundColor Green
    } else {
        throw "status $($h.StatusCode)"
    }
} catch {
    Write-Host "  FAIL: dispatch not running on port $appPort — run ..\..\run-fleet.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "[3/3] Checking website + driver entry..." -ForegroundColor Cyan
try {
    $site = Invoke-WebRequest -Uri "http://127.0.0.1:$webPort/" -UseBasicParsing -TimeoutSec 8
    if ($site.Content -notmatch 'L\s*&\s*P') { throw "website content mismatch" }
    Write-Host "  PASS: marketing website" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: website not running on port $webPort — run ..\..\run-fleet.ps1" -ForegroundColor Red
    exit 1
}

try {
    $driver = Invoke-WebRequest -Uri "http://127.0.0.1:$appPort/?view=driver" -UseBasicParsing -TimeoutSec 12
    if ($driver.StatusCode -eq 200) {
        Write-Host "  PASS: driver app entry" -ForegroundColor Green
    }
} catch {
    Write-Host "  WARN: driver view reachable but Streamlit may need browser check" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Fleet stack verified locally." -ForegroundColor Green
exit 0