# Full production deploy: Docker + DNS check + SSL + optional tunnel fallback
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)

Write-Host "=== L & P Freight Production Deploy ===" -ForegroundColor Cyan
Write-Host ""

# 1. Docker stack
Write-Host "[1/4] Building and starting Docker stack..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "Docker compose failed" }
Start-Sleep -Seconds 10

# 2. DNS check
Write-Host "[2/4] Checking DNS..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "setup-dns.ps1")
$dnsOk = $LASTEXITCODE -eq 0

# 3. SSL if DNS ready
if ($dnsOk) {
    Write-Host "[3/4] Issuing Let's Encrypt certificate..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "setup-ssl.ps1")
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "=== PRODUCTION LIVE ===" -ForegroundColor Green
        Write-Host "  https://dispatch.lpfreight.com/" -ForegroundColor Yellow
        Write-Host "  https://dispatch.lpfreight.com/app/" -ForegroundColor Yellow
        exit 0
    }
} else {
    Write-Host "[3/4] Skipping SSL — DNS not pointed at this server yet." -ForegroundColor Yellow
}

# 4. Tunnel fallback for immediate HTTPS
Write-Host "[4/4] Starting Cloudflare tunnel for immediate HTTPS access..." -ForegroundColor Cyan
Write-Host "(Use this until dispatch.lpfreight.com DNS is configured)" -ForegroundColor Gray
& (Join-Path $PSScriptRoot "setup-tunnel.ps1")