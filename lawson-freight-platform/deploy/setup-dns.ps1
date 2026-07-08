# Configure DNS for dispatch.lpfreight.com → this server
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)

function Load-DotEnv {
    $envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
    if (-not (Test-Path $envFile)) { return @{} }
    $vars = @{}
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $k, $v = $_ -split '=', 2
        $vars[$k.Trim()] = $v.Trim()
    }
    return $vars
}

$cfg = Load-DotEnv
$domain = $cfg["LP_SUBDOMAIN"]
if (-not $domain) { $domain = "dispatch.lpfreight.com" }
$ip = $cfg["SERVER_PUBLIC_IP"]
if (-not $ip) {
    try { $ip = (Invoke-WebRequest -Uri "https://api.ipify.org" -UseBasicParsing -TimeoutSec 10).Content.Trim() }
    catch { throw "Could not detect public IP. Set SERVER_PUBLIC_IP in .env" }
}

Write-Host ""
Write-Host "=== DNS Configuration for $domain ===" -ForegroundColor Cyan
Write-Host "Point this A record at your domain registrar (GoDaddy, Namecheap, Cloudflare, etc.):" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Type:  A" -ForegroundColor White
Write-Host "  Name:  dispatch" -ForegroundColor White
Write-Host "  Value: $ip" -ForegroundColor Green
Write-Host "  TTL:   300 (or Auto)" -ForegroundColor White
Write-Host ""

$current = $null
try {
    $resolved = [System.Net.Dns]::GetHostAddresses($domain) | ForEach-Object { $_.IPAddressToString }
    $current = $resolved -join ", "
} catch {
    $current = "(not resolving)"
}

Write-Host "Current DNS for ${domain}: $current" -ForegroundColor Gray
Write-Host "Required IP:              $ip" -ForegroundColor Gray

if ($current -match [regex]::Escape($ip)) {
    Write-Host "DNS is correctly pointed at this server." -ForegroundColor Green
    exit 0
}

# Cloudflare API auto-update if token provided
$cfToken = $cfg["CLOUDFLARE_API_TOKEN"]
$cfZone = $cfg["CLOUDFLARE_ZONE_ID"]
$rootDomain = $cfg["LP_DOMAIN"]

if ($cfToken -and $cfZone) {
    Write-Host "Attempting Cloudflare DNS update..." -ForegroundColor Cyan
    $headers = @{
        Authorization = "Bearer $cfToken"
        "Content-Type" = "application/json"
    }
    $listUri = "https://api.cloudflare.com/client/v4/zones/$cfZone/dns_records?type=A&name=$domain"
    $existing = Invoke-RestMethod -Uri $listUri -Headers $headers -Method Get
    $body = @{
        type = "A"
        name = "dispatch"
        content = $ip
        ttl = 300
        proxied = $false
    } | ConvertTo-Json

    if ($existing.result.Count -gt 0) {
        $recordId = $existing.result[0].id
        $updateUri = "https://api.cloudflare.com/client/v4/zones/$cfZone/dns_records/$recordId"
        $resp = Invoke-RestMethod -Uri $updateUri -Headers $headers -Method Put -Body $body
    } else {
        $createUri = "https://api.cloudflare.com/client/v4/zones/$cfZone/dns_records"
        $resp = Invoke-RestMethod -Uri $createUri -Headers $headers -Method Post -Body $body
    }

    if ($resp.success) {
        Write-Host "Cloudflare DNS updated: dispatch -> $ip" -ForegroundColor Green
        exit 0
    }
    Write-Host "Cloudflare update failed: $($resp.errors | ConvertTo-Json)" -ForegroundColor Red
}

Write-Host ""
Write-Host "NOTE: lpfreight.com currently resolves to a domain parking service (HugeDomains)." -ForegroundColor Yellow
Write-Host "You must own the domain and update DNS at your registrar before HTTPS will work." -ForegroundColor Yellow
Write-Host ""
Write-Host "After DNS propagates (5-30 min), run: .\deploy\setup-ssl.ps1" -ForegroundColor Cyan
exit 1