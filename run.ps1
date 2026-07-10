$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

$venvPath = Join-Path $PSScriptRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$preferredPython = @("3.12", "3.13", "3.11", "3")

function Get-PythonLauncherArg {
    foreach ($version in $preferredPython) {
        try {
            $null = & py "-$version" --version 2>$null
            if ($LASTEXITCODE -eq 0) {
                return "-$version"
            }
        } catch {
            continue
        }
    }

    throw "No compatible Python launcher target found. Install Python 3.11, 3.12, or 3.13."
}

function Test-CompatibleVenv {
    if (-not (Test-Path $pythonExe)) {
        return $false
    }

    $version = & $pythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    return @("3.11", "3.12", "3.13") -contains $version
}

if (-not (Test-CompatibleVenv)) {
    if (Test-Path $venvPath) {
        Write-Host "Rebuilding local Python virtual environment for Streamlit compatibility..." -ForegroundColor Yellow
        Remove-Item -LiteralPath $venvPath -Recurse -Force
    }

    $pythonArg = Get-PythonLauncherArg
    Write-Host "Creating local Python virtual environment..." -ForegroundColor Cyan
    py $pythonArg -m venv $venvPath
}

Write-Host "Installing/updating dependencies..." -ForegroundColor Cyan
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")

# Kill stale instance on 8501 (duplicate listeners cause 404 in browser)
$ErrorActionPreference = 'Continue'
Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
$ErrorActionPreference = 'Stop'

$appUrl = "http://127.0.0.1:8501"
Write-Host ('Starting L and P Freight Platform at ' + $appUrl) -ForegroundColor Green
Write-Host ('Open ' + $appUrl + ' in your browser. If you see 404, wait 5 sec and refresh.') -ForegroundColor Yellow
& $pythonExe -m streamlit run (Join-Path $PSScriptRoot 'app.py') --server.address 127.0.0.1 --server.port 8501 --server.headless false
