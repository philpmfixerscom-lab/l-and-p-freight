# Start HTTPS tunnel and save URL to .env (step 3 interim until custom domain DNS is live)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root

$cloudflared = Join-Path $PSScriptRoot "cloudflared.exe"
$python = Join-Path $root ".venv\Scripts\python.exe"
$port = 8502
$logFile = Join-Path $PSScriptRoot "tunnel.log"

if (-not (Test-Path $cloudflared)) {
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
        -OutFile $cloudflared -UseBasicParsing
}

# Ensure app is running
$listening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Write-Host "Starting Streamlit on port $port ..." -ForegroundColor Cyan
    Start-Process -FilePath $python -ArgumentList @(
        "-m", "streamlit", "run", "app.py",
        "--server.address", "0.0.0.0",
        "--server.port", "$port",
        "--server.headless", "true"
    ) -WindowStyle Hidden
    Start-Sleep -Seconds 8
}

# Stop prior tunnel
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

Write-Host "Starting Cloudflare HTTPS tunnel ..." -ForegroundColor Cyan
$errFile = Join-Path $PSScriptRoot "tunnel.err.log"
$proc = Start-Process -FilePath $cloudflared -ArgumentList @(
    "tunnel", "--url", "http://127.0.0.1:$port", "--loglevel", "info"
) -RedirectStandardOutput $logFile -RedirectStandardError $errFile -PassThru -WindowStyle Hidden

$tunnelUrl = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    $log = ""
    if (Test-Path $logFile) { $log += Get-Content $logFile -Raw -ErrorAction SilentlyContinue }
    if (Test-Path $errFile) { $log += Get-Content $errFile -Raw -ErrorAction SilentlyContinue }
    if ($log) {
        if ($log -match '(https://[a-z0-9-]+\.trycloudflare\.com)') {
            $tunnelUrl = $Matches[1]
            break
        }
    }
}

if (-not $tunnelUrl) {
    Write-Host "Tunnel started but URL not captured yet. Check $logFile" -ForegroundColor Yellow
    Write-Host "PID: $($proc.Id)" -ForegroundColor Gray
    exit 1
}

# Update .env with tunnel URL (keep LP_APP_URL as target domain)
$envFile = Join-Path $root ".env"
$lines = Get-Content $envFile
$updated = $false
$newLines = foreach ($line in $lines) {
    if ($line -match '^LP_TUNNEL_URL=') {
        $updated = $true
        "LP_TUNNEL_URL=$tunnelUrl"
    } else { $line }
}
if (-not $updated) { $newLines += "LP_TUNNEL_URL=$tunnelUrl" }
Set-Content -Path $envFile -Value $newLines -Encoding UTF8

Write-Host ""
Write-Host "HTTPS tunnel LIVE: $tunnelUrl" -ForegroundColor Green
Write-Host "Dispatch app:      $tunnelUrl" -ForegroundColor Green
Write-Host "Saved LP_TUNNEL_URL in .env" -ForegroundColor Gray
Write-Host ""
Write-Host "Target domain dispatch.lpfreight.com still needs DNS + domain purchase." -ForegroundColor Yellow