# R15 / E6: fingerprint dist\Slysh-Setup.exe for offline VM journal (SHA-256, size, git HEAD).
param(
    [string]$SetupPath = "",
    [string]$OutDir = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $SetupPath) {
    $SetupPath = Join-Path $Root "dist\Slysh-Setup.exe"
}
if (-not $OutDir) {
    $OutDir = Join-Path $Root "dist\acceptance"
}
$setup = Get-Item -LiteralPath $SetupPath
$version = $null
$payloadVersion = Join-Path $Root "dist\payload\version.json"
if (Test-Path -LiteralPath $payloadVersion) {
    $version = (Get-Content -LiteralPath $payloadVersion -Raw | ConvertFrom-Json).version
}
$gitHead = ""
try {
    Push-Location $Root
    $gitHead = (git rev-parse HEAD 2>$null)
} finally {
    Pop-Location
}
$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $setup.FullName
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outFile = Join-Path $OutDir "setup-fingerprint-$stamp.json"
$record = [ordered]@{
    setup_path       = $setup.FullName
    sha256           = $hash.Hash
    bytes            = $setup.Length
    last_write_time  = $setup.LastWriteTime.ToString("o")
    app_version      = $version
    git_head         = $gitHead
    recorded_utc     = (Get-Date).ToUniversalTime().ToString("o")
}
$record | ConvertTo-Json | Set-Content -LiteralPath $outFile -Encoding UTF8
Write-Host "write_setup_acceptance_record: $outFile"
Write-Host "  SHA256: $($hash.Hash)"
Write-Host "  Size:   $($setup.Length) bytes"
Write-Host "  Time:   $($setup.LastWriteTime)"
