# Issue Let's Encrypt certificate for dispatch.lpfreight.com
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)

function Load-DotEnv {
    $envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
    $vars = @{}
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
            $k, $v = $_ -split '=', 2
            $vars[$k.Trim()] = $v.Trim()
        }
    }
    return $vars
}

$cfg = Load-DotEnv
$domain = $cfg["LP_SUBDOMAIN"]
if (-not $domain) { $domain = "dispatch.lpfreight.com" }
$email = $cfg["LETSENCRYPT_EMAIL"]
if (-not $email) { $email = "admin@lpfreight.com" }
$staging = $cfg["CERTBOT_STAGING"] -eq "1"
$stagingFlag = if ($staging) { "--staging" } else { "" }

Write-Host "Requesting Let's Encrypt certificate for $domain ..." -ForegroundColor Cyan
if ($staging) { Write-Host "(staging mode — test cert only)" -ForegroundColor Yellow }

$certbotCmd = @(
    "compose", "run", "--rm", "--entrypoint", "certbot",
    "certbot", "certonly",
    "--webroot", "--webroot-path=/var/www/certbot",
    "--email", $email,
    "--agree-tos", "--no-eff-email",
    "-d", $domain
)
if ($stagingFlag) { $certbotCmd += $stagingFlag }

docker @certbotCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Certbot failed. Common causes:" -ForegroundColor Red
    Write-Host "  1. DNS for $domain does not point to this server yet" -ForegroundColor Yellow
    Write-Host "  2. Port 80 is not reachable from the internet" -ForegroundColor Yellow
    Write-Host "  3. Domain is not owned / still parked" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Run .\deploy\setup-dns.ps1 to verify DNS, then retry." -ForegroundColor Cyan
    exit 1
}

Write-Host "Certificate issued. Switching nginx to HTTPS config..." -ForegroundColor Green

$webContainer = "lp-freight-web"
docker exec $webContainer sh -c "rm -f /etc/nginx/conf.d/default.conf"
docker cp (Join-Path $PSScriptRoot "nginx.conf") "${webContainer}:/etc/nginx/conf.d/default.conf"
docker exec $webContainer nginx -s reload

Write-Host ""
Write-Host "HTTPS live at: https://$domain/" -ForegroundColor Green
Write-Host "Dispatch app:  https://$domain/app/" -ForegroundColor Green