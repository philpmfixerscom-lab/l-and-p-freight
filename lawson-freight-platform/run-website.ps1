$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $repoRoot "run-fleet.ps1")