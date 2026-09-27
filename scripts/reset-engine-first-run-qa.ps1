# QA: сброс first-run локальных пакетов + кэша uv (полное скачивание torch с сети).
# Запуск (PowerShell): powershell -ExecutionPolicy Bypass -File scripts\reset-engine-first-run-qa.ps1
# Опции: -InstallRoot "C:\Users\YOU\AppData\Local\Programs\Slysh"  -SkipUvCache

param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Programs\Slysh"),
    [switch]$SkipUvCache
)

$ErrorActionPreference = "Stop"
$AppData = Join-Path $env:LOCALAPPDATA "Slysh"
$UvCache = Join-Path $env:LOCALAPPDATA "uv"

Write-Host "Stop Slysh..."
Stop-Process -Name "Slysh", "pythonw" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

if (Test-Path -LiteralPath $InstallRoot) {
    $venv = Join-Path $InstallRoot ".venv"
    if (Test-Path -LiteralPath $venv) {
        Write-Host "Remove venv: $venv"
        Remove-Item -LiteralPath $venv -Recurse -Force
    }
} else {
    Write-Host "Install root not found (skip venv): $InstallRoot"
}

$flags = @(
    "setup-engine-later",
    "setup-pending-model-download",
    "prompt-engine-setup"
)
foreach ($name in $flags) {
    $p = Join-Path $AppData $name
    if (Test-Path -LiteralPath $p) {
        Remove-Item -LiteralPath $p -Force
        Write-Host "Removed $p"
    }
}

$log = Join-Path $AppData "logs\engine-setup.log"
if (Test-Path -LiteralPath $log) {
    Remove-Item -LiteralPath $log -Force
    Write-Host "Removed $log"
}

if (-not $SkipUvCache) {
    if (Test-Path -LiteralPath $UvCache) {
        Write-Host "Remove uv cache (full re-download): $UvCache"
        Remove-Item -LiteralPath $UvCache -Recurse -Force
    } else {
        Write-Host "No uv cache at $UvCache"
    }
}

Write-Host ""
Write-Host "Done. Next:"
Write-Host "  1) Start Slysh from $InstallRoot\Slysh.exe (or reinstall Setup)."
Write-Host "  2) Optional: set SLYSH_ENGINE_INSTALL_NO_CACHE=1 for this session (uv sync --no-cache from UI)."
Write-Host "  3) First-run: Local -> confirm -> Start (expect 10-30 min download, VPN off)."
