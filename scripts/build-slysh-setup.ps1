# Compile dist\Slysh-Setup.exe via Inno Setup (ISCC).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Iss = Join-Path $Root "installer\Slysh.iss"

function Resolve-Iscc {
    $candidates = @(
        (Join-Path $env:LocalAppData "Programs\Inno Setup 6\ISCC.exe"),
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path -LiteralPath $path) {
            return $path
        }
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        return $cmd.Source
    }
    throw @"
ISCC.exe (Inno Setup 6) not found.
Install from https://jrsoftware.org/isinfo.php
Typical path: $env:LocalAppData\Programs\Inno Setup 6\ISCC.exe
"@
}

$Payload = Join-Path $Root "dist\payload"
if (-not (Test-Path -LiteralPath (Join-Path $Payload ".venv\Scripts\python.exe"))) {
    throw "Missing $Payload. Run scripts\build-installer-payload.ps1 first."
}

$pyproject = Join-Path $Root "pyproject.toml"
$pyText = Get-Content -LiteralPath $pyproject -Raw -Encoding UTF8
if ($pyText -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "Could not read version from pyproject.toml"
}
$AppVersion = $Matches[1]
$versionParts = $AppVersion.Split(".")
while ($versionParts.Count -lt 4) {
    $versionParts += "0"
}
$VersionInfo = ($versionParts[0..3] -join ".")

$Iscc = Resolve-Iscc
Write-Host "Using $Iscc (AppVersion=$AppVersion)"
& $Iscc "/DAppVersion=$AppVersion" "/DVersionInfoVersion=$VersionInfo" $Iss
if ($LASTEXITCODE -ne 0) {
    throw "ISCC failed with exit code $LASTEXITCODE"
}

$Out = Join-Path $Root "dist\Slysh-Setup.exe"
if (-not (Test-Path -LiteralPath $Out)) {
    throw "Expected output missing: $Out"
}
Write-Host "Setup OK: $Out"
