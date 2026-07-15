$ErrorActionPreference = "Stop"

# Backward-compatible alias — Lawson tabs live in the main app now.
# Prefer: .\run.ps1  or  .\run-fleet.ps1
Write-Host "run_lawson.ps1 is an alias for the main platform (port 8502)." -ForegroundColor Cyan
Write-Host "Starting via run.ps1 ..." -ForegroundColor Gray
& (Join-Path $PSScriptRoot "run.ps1")
