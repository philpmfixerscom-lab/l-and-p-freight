# Cloudflare Quick Tunnel — instant HTTPS while DNS/domain is being configured
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    Write-Host "Installing cloudflared..." -ForegroundColor Cyan
    winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
    $cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cloudflared) { throw "cloudflared install failed. Download from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" }
}

$port = if ($env:WEB_PORT) { $env:WEB_PORT } else { "80" }

# Ensure docker stack is running
$running = docker compose ps --status running -q 2>$null
if (-not $running) {
    Write-Host "Starting Docker stack first..." -ForegroundColor Cyan
    docker compose up -d --build
    Start-Sleep -Seconds 8
}

Write-Host ""
Write-Host "Starting Cloudflare Quick Tunnel → http://127.0.0.1:$port" -ForegroundColor Green
Write-Host "You will get a free https://*.trycloudflare.com URL with valid HTTPS." -ForegroundColor Yellow
Write-Host "Copy that URL into .env as LP_APP_URL until dispatch.lpfreight.com DNS is live." -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop the tunnel." -ForegroundColor Gray
Write-Host ""

& cloudflared tunnel --url "http://127.0.0.1:$port"