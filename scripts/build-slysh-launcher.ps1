# Build installer/prebuilt/Slysh.exe from launcher/Slysh.c (optional; needs VS cl.exe).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LauncherDir = Join-Path $Root "launcher"
$PrebuiltDir = Join-Path $Root "installer\prebuilt"
$Out = Join-Path $PrebuiltDir "Slysh.exe"
$Src = Join-Path $LauncherDir "Slysh.c"

New-Item -ItemType Directory -Path $PrebuiltDir -Force | Out-Null

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path -LiteralPath $vswhere)) {
    Write-Error "vswhere not found. Install VS Build Tools or build manually (see launcher/README.md)."
}

$vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) {
    Write-Error "VC tools not found. Install C++ build tools or build manually (see launcher/README.md)."
}

$vcvars = Join-Path $vsPath "VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path -LiteralPath $vcvars)) {
    Write-Error "vcvars64.bat not found under $vsPath"
}

$cmd = @"
call "$vcvars" >nul && cd /d "$LauncherDir" && cl /nologo /utf-8 /O2 /W4 Slysh.c /Fe:"$Out" /link /SUBSYSTEM:WINDOWS shlwapi.lib user32.lib shell32.lib gdi32.lib dwmapi.lib
"@
cmd /c $cmd
if ($LASTEXITCODE -ne 0) {
    throw "cl failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $Out)) {
    throw "Output missing: $Out"
}
Write-Host "Built $Out"
