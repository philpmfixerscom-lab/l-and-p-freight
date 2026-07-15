# Quick start — no pip install. Double-click or: powershell -File start.ps1
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$appPy = Join-Path $PSScriptRoot 'app.py'

if (-not (Test-Path $pythonExe)) {
    Write-Host 'No .venv found. Run run.ps1 first to set up.' -ForegroundColor Red
    exit 1
}

Get-NetTCPConnection -LocalPort 8502 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

$url = 'http://127.0.0.1:8502'
Write-Host "L and P Freight Platform -> $url" -ForegroundColor Green
& $pythonExe -m streamlit run $appPy --server.address 127.0.0.1 --server.port 8502 --server.headless false