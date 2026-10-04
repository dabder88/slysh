# E.6: verify installed/payload layout offline-ready (run on clean VM or against dist\payload).
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [switch]$RequireWheelhouse,
    [switch]$ProbeOfflineUiSync,
    [string]$ResultJson = ""
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath $InstallRoot).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Uv = Join-Path $Root "bin\uv.exe"
$Ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
$Exe = Join-Path $Root "Slysh.exe"
$Wheelhouse = Join-Path $Root "wheelhouse"
$PyvenvCfg = Join-Path $Root ".venv\pyvenv.cfg"
$Notices = Join-Path $Root "licenses\THIRD-PARTY-NOTICES.md"
$EulaRu = Join-Path $Root "licenses\Slysh-EULA-RU.txt"
$EulaEn = Join-Path $Root "licenses\Slysh-EULA-EN.txt"

$checks = [ordered]@{}

function Fail($msg) {
    $checks["error"] = $msg
    Write-ResultAndExit -Ok $false -Message $msg
}

function Write-ResultAndExit {
    param([bool]$Ok, [string]$Message)
    if ($ResultJson) {
        $payload = @{
            ok               = $Ok
            install_root     = $Root
            wheelhouse_count = $whCount
            checks           = $checks
            message          = $Message
            timestamp_utc    = (Get-Date).ToUniversalTime().ToString("o")
        }
        $payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResultJson -Encoding UTF8
    }
    if (-not $Ok) {
        Write-Error "e6-offline-vm-verify: FAIL: $Message"
        exit 1
    }
    Write-Host "e6-offline-vm-verify: OK ($Root, wheelhouse=$whCount)"
    exit 0
}

$whCount = @(Get-ChildItem -LiteralPath $Wheelhouse -Filter "*.whl" -ErrorAction SilentlyContinue).Count
$checks["wheelhouse_count"] = $whCount

@(
    @{ Path = $Python; Name = "ui_python" }
    @{ Path = $Pythonw; Name = "ui_pythonw" }
    @{ Path = $Uv; Name = "uv" }
    @{ Path = $Ffmpeg; Name = "ffmpeg" }
    @{ Path = $Exe; Name = "Slysh.exe" }
    @{ Path = (Join-Path $Root "Slysh.bat"); Name = "Slysh.bat" }
    @{ Path = (Join-Path $Root "pyproject.toml"); Name = "pyproject.toml" }
    @{ Path = (Join-Path $Root "uv.lock"); Name = "uv.lock" }
    @{ Path = (Join-Path $Root "src\slysh\app.py"); Name = "src_slysh" }
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_.Path)) {
        Fail "missing $($_.Path)"
    }
    $checks[$_.Name] = "present"
}

$runtimePython = Join-Path $Root "runtime\python"
if (-not (Test-Path -LiteralPath $runtimePython)) {
    Fail "missing runtime\python"
}
$bundledPy = Get-ChildItem -LiteralPath $runtimePython -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $bundledPy) {
    Fail "no bundled python.exe under runtime\python"
}
$checks["runtime_python"] = $bundledPy.FullName

if ($RequireWheelhouse -and $whCount -lt 10) {
    Fail "wheelhouse needs 10+ wheels, got $whCount"
}
if ($whCount -lt 10) {
    Write-Warning "wheelhouse has $whCount wheels (offline repair may be limited)"
}

if (-not (Test-Path -LiteralPath $Notices)) {
    Fail "missing licenses\THIRD-PARTY-NOTICES.md (rebuild payload after THIRD_PARTY_NOTICES.md update)"
}
if (-not (Test-Path -LiteralPath $EulaRu)) {
    Fail "missing licenses\Slysh-EULA-RU.txt (rebuild payload; see installer/LICENSE-RU.txt)"
}
if (-not (Test-Path -LiteralPath $EulaEn)) {
    Fail "missing licenses\Slysh-EULA-EN.txt (rebuild payload; see installer/LICENSE-EN.txt)"
}
$checks["third_party_notices"] = "present"
$checks["slysh_eula_ru"] = "present"
$checks["slysh_eula_en"] = "present"

if (-not (Test-Path -LiteralPath $PyvenvCfg)) {
    Fail "missing .venv\pyvenv.cfg"
}
$homeLine = $null
foreach ($line in (Get-Content -LiteralPath $PyvenvCfg)) {
    if ($line -match '^home\s*=\s*(.+)$') {
        $homeLine = $Matches[1].Trim()
        break
    }
}
if (-not $homeLine) {
    Fail "pyvenv.cfg missing home ="
}
$homePath = $null
try {
    $homePath = (Resolve-Path -LiteralPath $homeLine).Path
} catch {
    Fail "pyvenv.cfg home not found: $homeLine"
}
$rootNorm = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\')
if (-not $homePath.StartsWith($rootNorm, [StringComparison]::OrdinalIgnoreCase)) {
    Fail "pyvenv.cfg home must be under install root; home=$homePath root=$rootNorm"
}
if ($homeLine -match 'Roaming' -and $homeLine -match 'uv') {
    Fail "pyvenv.cfg must not point at user uv cache: $homeLine"
}
$checks["pyvenv_home"] = $homePath

$env:SLYSH_INSTALL_ROOT = $Root
$env:PATH = (Join-Path $Root "bin") + ";" + $env:PATH
$env:GIGAAM_SKIP_ENGINE = "1"
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue

Push-Location $Root
try {
    & $Python -c "import slysh"
    if ($LASTEXITCODE -ne 0) { Fail "python import slysh" }
    $checks["import_slysh_python"] = "ok"

    & $Pythonw -c 'import slysh'
    if ($LASTEXITCODE -ne 0) { Fail "pythonw import slysh" }
    $checks["import_slysh_pythonw"] = "ok"

    & $Python -c "import torch"
    if ($LASTEXITCODE -eq 0) { Fail "UI venv must not import torch" }
    $checks["ui_no_torch"] = "ok"

    if ($ProbeOfflineUiSync) {
        if ($whCount -lt 10) {
            Fail "ProbeOfflineUiSync requires wheelhouse with 10+ wheels"
        }
        $syncArgs = @(
            "sync",
            "--no-editable",
            "--find-links", $Wheelhouse,
            "--offline",
            "--no-progress"
        )
        & $Uv @syncArgs
        if ($LASTEXITCODE -ne 0) {
            Fail "uv sync --offline --find-links wheelhouse failed"
        }
        $checks["offline_ui_sync"] = "ok"
    }
} finally {
    Pop-Location
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$SmokePy = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $SmokePy)) { $SmokePy = "python" }
$Sanity = Join-Path $repoRoot "scripts\check_payload_sanity.py"
if ((Resolve-Path -LiteralPath $Root).Path -eq (Join-Path $repoRoot "dist\payload") -and (Test-Path -LiteralPath $Sanity)) {
    & $SmokePy $Sanity
    if ($LASTEXITCODE -ne 0) { Fail "check_payload_sanity" }
    $checks["payload_sanity"] = "ok"
}

Write-ResultAndExit -Ok $true -Message "OK"
