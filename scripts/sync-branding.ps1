# Copy runtime branding from design/logo/final into web/ and repo root.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Final = Join-Path $Root "design\logo\final"
$Branding = Join-Path $Root "web\branding"

$maps = @(
    @{
        Src = Join-Path $Final "png\sizes\slysh-symbol-48.png"
        Dst = Join-Path $Branding "slysh-mark-48.png"
    },
    @{
        Src = Join-Path $Final "png\sizes\slysh-symbol-32.png"
        Dst = Join-Path $Branding "favicon-32.png"
    },
    @{
        Src = Join-Path $Final "ico\slysh-original.ico"
        Dst = Join-Path $Root "slysh.ico"
    }
)

New-Item -ItemType Directory -Force -Path $Branding | Out-Null

foreach ($m in $maps) {
    if (-not (Test-Path $m.Src)) {
        Write-Error "Missing source: $($m.Src). Run design\logo\final\build_exact_assets.py first."
    }
    Copy-Item -Path $m.Src -Destination $m.Dst -Force
    Write-Host "OK $($m.Dst)"
}

Write-Host "Branding sync complete."
