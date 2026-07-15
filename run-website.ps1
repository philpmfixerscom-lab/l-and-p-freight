$ErrorActionPreference = "Stop"
# Website + dispatch fleet stack
& (Join-Path $PSScriptRoot "run-fleet.ps1")
