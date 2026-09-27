# Silent install dist\Slysh-Setup.exe to F:\ProjectsAI\Slysh-test (maintainer smoke).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Setup = Join-Path $Root "dist\Slysh-Setup.exe"
$Target = "F:\ProjectsAI\Slysh-test"

if (-not (Test-Path -LiteralPath $Setup)) {
    throw "Missing $Setup. Run scripts\build-slysh-setup.ps1 first."
}

$unins = Join-Path $Target "unins000.exe"
if (Test-Path -LiteralPath $unins) {
    Write-Host "Uninstalling previous copy in $Target ..."
    $p = Start-Process -FilePath $unins -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Write-Warning "Uninstaller exit code $($p.ExitCode); continuing with setup"
    }
    Start-Sleep -Seconds 2
}

New-Item -ItemType Directory -Path $Target -Force | Out-Null

Write-Host "Installing to $Target ..."
$proc = Start-Process -FilePath $Setup -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/DIR=$Target"
) -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    throw "Setup failed with exit code $($proc.ExitCode)"
}

$pyvenv = Join-Path $Target ".venv\pyvenv.cfg"
$python = Join-Path $Target ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Install missing $python"
}

$homeLine = Get-Content -LiteralPath $pyvenv -Encoding UTF8 | Where-Object { $_ -match '^home = ' } | Select-Object -First 1
Write-Host "pyvenv: $homeLine"
if ($homeLine -notlike "*$Target*") {
    Write-Host "Note: home may be repaired on first Slysh.exe launch (portable venv fix)."
}

& $python -c "import slysh; print('import ok')"
if ($LASTEXITCODE -ne 0) {
    throw "slysh import failed in installed copy"
}

Write-Host "Installed OK: $Target"
