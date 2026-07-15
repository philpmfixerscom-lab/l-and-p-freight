$ErrorActionPreference = "Stop"

# Repo root = parent of scripts/ (single package tree)
$root = Split-Path $PSScriptRoot -Parent
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
$appPort = if ($env:APP_PORT) { $env:APP_PORT } else { "8502" }
$webPort = if ($env:WEB_PORT) { $env:WEB_PORT } else { "8080" }

if (-not (Test-Path $pythonExe)) {
    Write-Host "FAIL: Run .\run.ps1 first to create .venv" -ForegroundColor Red
    exit 1
}

Write-Host "=== Fleet Local Verification ===" -ForegroundColor Cyan
Write-Host "Root: $root" -ForegroundColor Gray

Write-Host "[1/4] Package integrity (lp_helpers sources)..." -ForegroundColor Cyan
$required = @(
    "driver_mobile.py", "database.py", "emergency_alerts.py", "engines.py",
    "traccar_live.py", "load_board.py", "mobile_web.py", "ui_components.py",
    "ui_theme.py", "bol_export.py", "lawson_profile.py", "__init__.py"
)
$helpers = Join-Path $root "lp_helpers"
foreach ($name in $required) {
    $path = Join-Path $helpers $name
    if (-not (Test-Path $path)) {
        Write-Host "  FAIL: missing $path" -ForegroundColor Red
        exit 1
    }
}
if (Test-Path (Join-Path $root "lawson-freight-platform\app.py")) {
    Write-Host "  FAIL: nested lawson-freight-platform/ still present - single package tree required" -ForegroundColor Red
    exit 1
}
Write-Host "  PASS: package sources" -ForegroundColor Green

Write-Host "[2/4] Running pytest..." -ForegroundColor Cyan
Push-Location $root
& $pythonExe -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }
Pop-Location
Write-Host "  PASS: all tests" -ForegroundColor Green

Write-Host "[3/4] Checking dispatch health..." -ForegroundColor Cyan
try {
    $h = Invoke-WebRequest -Uri "http://127.0.0.1:$appPort/_stcore/health" -UseBasicParsing -TimeoutSec 8
    if ($h.StatusCode -eq 200) {
        Write-Host "  PASS: dispatch health" -ForegroundColor Green
    } else {
        throw "status $($h.StatusCode)"
    }
} catch {
    Write-Host "  FAIL: dispatch not running on port $appPort - run .\run-fleet.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "[4/4] Checking website + driver entry..." -ForegroundColor Cyan
try {
    $site = Invoke-WebRequest -Uri "http://127.0.0.1:$webPort/" -UseBasicParsing -TimeoutSec 8
    if ($site.Content -notmatch 'L\s*&\s*P') { throw "website content mismatch" }
    Write-Host "  PASS: marketing website" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: website not running on port $webPort - run .\run-fleet.ps1" -ForegroundColor Red
    exit 1
}

try {
    $driver = Invoke-WebRequest -Uri "http://127.0.0.1:$appPort/?view=driver" -UseBasicParsing -TimeoutSec 12
    if ($driver.StatusCode -eq 200) {
        Write-Host "  PASS: driver app entry" -ForegroundColor Green
    }
} catch {
    Write-Host "  FAIL: driver entry not reachable - $($_)" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "All fleet checks passed." -ForegroundColor Green
