# L & P Freight — production deploy via Docker
# Usage: .\deploy.ps1
# Set LP_APP_URL in .env before deploying (e.g. https://yourdomain.com)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is required. Install Docker Desktop and retry." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example — set LP_APP_URL to your public domain." -ForegroundColor Yellow
    }
}

Write-Host "Building and starting L & P Freight (website + app)..." -ForegroundColor Cyan
docker compose up --build -d

if ($LASTEXITCODE -eq 0) {
    $port = if ($env:WEB_PORT) { $env:WEB_PORT } else { "80" }
    Write-Host ""
    Write-Host "Deployed successfully." -ForegroundColor Green
    Write-Host "  Website:  http://localhost:$port/" -ForegroundColor Yellow
    Write-Host "  App:      http://localhost:$port/app/" -ForegroundColor Yellow
    Write-Host "  Health:   http://localhost:$port/healthz" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Set LP_APP_URL in .env to your public URL for PWA install links." -ForegroundColor Gray
}