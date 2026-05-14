$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "build_local_exe.ps1")
& (Join-Path $PSScriptRoot "build_web_exe.ps1")

Write-Host "OK. Wygenerowano oba pliki EXE w: $PSScriptRoot"
