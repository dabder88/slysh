# R15 / E6 / plan-fix-3 I8: fingerprint Setup artifacts (SHA-256, size, git HEAD).
param(
    [string[]]$SetupPaths = @(),
    [string]$OutDir = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if ($SetupPaths.Count -eq 0) {
    $pyproject = Join-Path $Root "pyproject.toml"
    $appVer = "0.0.0"
    if (Test-Path -LiteralPath $pyproject) {
        $pyText = Get-Content -LiteralPath $pyproject -Raw -Encoding UTF8
        if ($pyText -match '(?m)^version\s*=\s*"([^"]+)"') {
            $appVer = $Matches[1]
        }
    }
    $SetupPaths = @(
        (Join-Path $Root "dist\Slysh-Setup-$appVer-ru.exe"),
        (Join-Path $Root "dist\Slysh-Setup-$appVer-en.exe")
    )
}
if (-not $OutDir) {
    $OutDir = Join-Path $Root "dist\acceptance"
}
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
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$artifacts = @()
foreach ($setupPath in $SetupPaths) {
    if (-not (Test-Path -LiteralPath $setupPath)) {
        Write-Warning "write_setup_acceptance_record: skip missing $setupPath"
        continue
    }
    $setup = Get-Item -LiteralPath $setupPath
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $setup.FullName
    $artifacts += [ordered]@{
        setup_path      = $setup.FullName
        sha256          = $hash.Hash
        bytes           = $setup.Length
        last_write_time = $setup.LastWriteTime.ToString("o")
    }
    Write-Host "write_setup_acceptance_record: $($setup.FullName)"
    Write-Host "  SHA256: $($hash.Hash)"
    Write-Host "  Size:   $($setup.Length) bytes"
    Write-Host "  Time:   $($setup.LastWriteTime)"
}
if ($artifacts.Count -eq 0) {
    throw "No Setup executables found under dist\"
}
$record = [ordered]@{
    artifacts    = $artifacts
    app_version  = $version
    git_head     = $gitHead
    recorded_utc = (Get-Date).ToUniversalTime().ToString("o")
}
$outFile = Join-Path $OutDir "setup-fingerprint-$stamp.json"
$latest = Join-Path $OutDir "setup-fingerprint-latest.json"
$json = $record | ConvertTo-Json -Depth 4
Set-Content -LiteralPath $outFile -Value $json -Encoding UTF8
Set-Content -LiteralPath $latest -Value $json -Encoding UTF8
Write-Host "write_setup_acceptance_record: $outFile"
