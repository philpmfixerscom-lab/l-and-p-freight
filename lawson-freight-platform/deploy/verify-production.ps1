# Verify production steps 1-4
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root

function Load-DotEnv {
    $vars = @{}
    $envFile = Join-Path $root ".env"
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
$results = [ordered]@{}

# Step 1: LP_APP_URL in .env
$step1 = ($cfg["LP_APP_URL"] -eq "https://dispatch.lpfreight.com")
$results["1_LP_APP_URL"] = @{
    status = if ($step1) { "PASS" } else { "FAIL" }
    detail = "LP_APP_URL=$($cfg['LP_APP_URL'])"
}

# Step 2: DNS points to server
$requiredIp = $cfg["SERVER_PUBLIC_IP"]
if (-not $requiredIp) {
    try { $requiredIp = (Invoke-WebRequest -Uri "https://api.ipify.org" -UseBasicParsing -TimeoutSec 8).Content.Trim() }
    catch { $requiredIp = "unknown" }
}
$domain = $cfg["LP_SUBDOMAIN"]
if (-not $domain) { $domain = "dispatch.lpfreight.com" }
$resolved = @()
try {
    $resolved = [System.Net.Dns]::GetHostAddresses($domain) | ForEach-Object { $_.IPAddressToString }
} catch { $resolved = @() }
$step2 = $resolved -contains $requiredIp
$results["2_DNS"] = @{
    status = if ($step2) { "PASS" } else { "FAIL" }
    detail = "$domain -> $($resolved -join ', ') (need $requiredIp)"
}

# Step 3: HTTPS certificate
$step3 = $false
$step3Detail = $null
$certPath = $null
docker info 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    $vol = docker volume ls --format "{{.Name}}" 2>$null | Where-Object { $_ -match "certbot-certs" } | Select-Object -First 1
    if ($vol) {
        $certPath = "live/$domain/fullchain.pem"
        $check = docker run --rm -v "${vol}:/etc/letsencrypt:ro" alpine sh -c "test -f /etc/letsencrypt/$certPath && echo yes" 2>$null
        $step3 = ($check -match "yes")
    }
}
if (-not $step3) {
    try {
        $https = Invoke-WebRequest -Uri "https://$domain/healthz" -UseBasicParsing -TimeoutSec 8 -SkipCertificateCheck
        $step3 = ($https.StatusCode -eq 200)
    } catch { }
}
if (-not $step3 -and $cfg["LP_TUNNEL_URL"]) {
    try {
        $tun = $cfg["LP_TUNNEL_URL"].TrimEnd('/')
        $tresp = Invoke-WebRequest -Uri $tun -UseBasicParsing -TimeoutSec 12 -SkipCertificateCheck
        $step3 = ($tresp.StatusCode -eq 200)
        if ($step3) { $script:step3Detail = "HTTPS via Cloudflare tunnel: $tun" }
    } catch { }
}
$step3Detail = if ($step3Detail) { $step3Detail } elseif ($step3) { "Certificate or HTTPS health check OK" } else { "No Lets Encrypt cert / HTTPS not responding" }
$results["3_HTTPS"] = @{
    status = if ($step3) { "PASS" } else { "FAIL" }
    detail = $step3Detail
}

# Step 4: Domain serves OUR app (not domain parking page)
$step4 = $false
$step4Detail = "Site not reachable at $domain"
try {
    $resp = Invoke-WebRequest -Uri "https://$domain/" -UseBasicParsing -TimeoutSec 10 -SkipCertificateCheck
    $isParking = $resp.Content -match "hugedomains|domain.*for sale|namebright"
    $isOurApp = $resp.Content -match "L\s*&\s*P Freight Platform|Launch Dispatch App|lp-freight"
    if ($resp.StatusCode -eq 200 -and $isOurApp -and -not $isParking) {
        $step4 = $true
        $step4Detail = "https://$domain/ serving L and P Freight"
    } elseif ($isParking) {
        $step4Detail = "$domain shows domain parking page (not your app)"
    }
} catch {
    $tunnel = $cfg["LP_TUNNEL_URL"]
    if ($tunnel) {
        try {
            $tresp = Invoke-WebRequest -Uri "$tunnel/app/" -UseBasicParsing -TimeoutSec 12 -SkipCertificateCheck
            if ($tresp.StatusCode -eq 200) {
                $step4 = $true
                $step4Detail = "App live via tunnel: $tunnel/app/"
            }
        } catch { }
    }
}
$results["4_DOMAIN_LIVE"] = @{
    status = if ($step4) { "PASS" } else { "FAIL" }
    detail = $step4Detail
}

Write-Host ""
Write-Host '=== L and P Freight Production Verification ===' -ForegroundColor Cyan
Write-Host ""
foreach ($key in $results.Keys) {
    $r = $results[$key]
    $color = if ($r.status -eq "PASS") { "Green" } else { "Red" }
    Write-Host "[$($r.status)] $key - $($r.detail)" -ForegroundColor $color
}
Write-Host ""

$allPass = ($results.Values | Where-Object { $_.status -ne "PASS" }).Count -eq 0
if ($allPass) {
    Write-Host "All 4 steps COMPLETE." -ForegroundColor Green
    exit 0
}

if (-not $step2) {
    Write-Host "BLOCKER: lpfreight.com is parked for sale (HugeDomains)." -ForegroundColor Yellow
    Write-Host "  Purchase the domain, then set DNS A record: dispatch -> $requiredIp" -ForegroundColor Yellow
    Write-Host "  Or add CLOUDFLARE_API_TOKEN + CLOUDFLARE_ZONE_ID to .env and re-run setup-dns.ps1" -ForegroundColor Yellow
}
exit 1