# Native production (no Docker) — Streamlit + Cloudflare HTTPS tunnel
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)

$venvPython = Join-Path $PSScriptRoot ".." ".venv\Scripts\python.exe" | Resolve-Path
$cloudflared = Join-Path $PSScriptRoot "cloudflared.exe"

if (-not (Test-Path $cloudflared)) {
    Write-Host "Downloading cloudflared..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
        -OutFile $cloudflared -UseBasicParsing
}

# Load .env
$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $k, $v = $_ -split '=', 2
        Set-Item -Path "env:$($k.Trim())" -Value $v.Trim()
    }
}

$port = 8502
$ErrorActionPreference = 'Continue'
Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
$ErrorActionPreference = 'Stop'

Write-Host "Starting dispatch app on 0.0.0.0:$port ..." -ForegroundColor Cyan
$streamlitJob = Start-Process -FilePath $venvPython -ArgumentList @(
    "-m", "streamlit", "run", "app.py",
    "--server.address", "0.0.0.0",
    "--server.port", "$port",
    "--server.headless", "true"
) -PassThru -WindowStyle Hidden

Start-Sleep -Seconds 6

Write-Host "Starting Cloudflare HTTPS tunnel..." -ForegroundColor Green
Write-Host "Watch for your https://*.trycloudflare.com URL below." -ForegroundColor Yellow
Write-Host "Update .env LP_APP_URL with that URL until custom domain DNS is live." -ForegroundColor Yellow
Write-Host ""

& $cloudflared tunnel --url "http://127.0.0.1:$port"