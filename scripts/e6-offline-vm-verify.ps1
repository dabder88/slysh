# E.6: verify installed/payload layout offline-ready (run on clean VM or against dist\payload).
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [switch]$RequireWheelhouse
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath $InstallRoot).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Uv = Join-Path $Root "bin\uv.exe"
$Ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
$Exe = Join-Path $Root "Slysh.exe"
$Wheelhouse = Join-Path $Root "wheelhouse"

function Fail($msg) {
    Write-Error "e6-offline-vm-verify: FAIL: $msg"
    exit 1
}

@($Python, $Pythonw, $Uv, $Ffmpeg, $Exe, (Join-Path $Root "Slysh.bat")) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) { Fail "missing $_" }
}

$wh = @(Get-ChildItem -LiteralPath $Wheelhouse -Filter "*.whl" -ErrorAction SilentlyContinue).Count
if ($RequireWheelhouse -and $wh -lt 10) { Fail "wheelhouse needs 10+ wheels, got $wh" }
if ($wh -lt 10) { Write-Warning "wheelhouse has $wh wheels (offline repair may be limited)" }

$env:SLYSH_INSTALL_ROOT = $Root
$env:PATH = (Join-Path $Root "bin") + ";" + $env:PATH
$env:GIGAAM_SKIP_ENGINE = "1"
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue

Push-Location $Root
try {
    & $Python -c "import slysh"
    if ($LASTEXITCODE -ne 0) { Fail "python import slysh" }
    & $Pythonw -c 'import slysh'
    if ($LASTEXITCODE -ne 0) { Fail "pythonw import slysh" }

    & $Python -c "import torch"
    if ($LASTEXITCODE -eq 0) { Fail "UI venv must not import torch" }
} finally {
    Pop-Location
}

$SmokePy = Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $SmokePy)) { $SmokePy = "python" }
$Sanity = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\check_payload_sanity.py"
if (Test-Path -LiteralPath $Sanity) {
    & $SmokePy $Sanity
    if ($LASTEXITCODE -ne 0) { Fail "check_payload_sanity" }
}

Write-Host "e6-offline-vm-verify: OK ($Root, wheelhouse=$wh)"
exit 0
