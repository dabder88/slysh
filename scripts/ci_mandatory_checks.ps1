# Wave F: mandatory checks without local tests/ tree (prod-launch CI + maintainer).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Host "=== check-web-js ==="
powershell -NoProfile -File (Join-Path $Root "scripts\check-web-js.ps1")

Write-Host "=== build:css ==="
npm ci
npm run build:css

Write-Host "=== ci/check_import_path.py ==="
& $Python (Join-Path $Root "ci\check_import_path.py")

Write-Host "=== ci/check_ui_imports.py ==="
& $Python (Join-Path $Root "ci\check_ui_imports.py")

Write-Host "=== ci/check_gemini_cli_prompt.py ==="
& $Python (Join-Path $Root "ci\check_gemini_cli_prompt.py")

Write-Host "=== audit_git_secrets.ps1 ==="
powershell -NoProfile -File (Join-Path $Root "scripts\audit_git_secrets.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "audit_git_secrets failed"
}

$Smokes = @(
    "scripts\smoke_engine_cancel_sequence.py",
    "scripts\smoke_providers_secret_contract.py",
    "scripts\smoke_open_path_api.py",
    "scripts\smoke_ui_auth_session.py",
    "scripts\smoke_loopback_host_origin.py",
    "scripts\smoke_coordinator_queued_cancel.py",
    "scripts\smoke_updates_sha256.py",
    "scripts\smoke_runtime_env_slots.py"
)
foreach ($rel in $Smokes) {
    $path = Join-Path $Root $rel
    if (-not (Test-Path $path)) {
        throw "missing smoke: $rel"
    }
    Write-Host "=== $rel ==="
    & $Python $path
    if ($LASTEXITCODE -ne 0) {
        throw "smoke failed: $rel"
    }
}

if (Test-Path (Join-Path $Root "tests")) {
    Write-Host "=== pytest tests (optional local) ==="
    $env:PYTHONPATH = "src"
    $env:GIGAAM_SKIP_ENGINE = "1"
    $env:GIGAAM_UI_AUTH = "0"
    $env:GIGAAM_LOOPBACK_STRICT = "0"
    $env:SLYSH_DISABLE_OPENAPI = "1"
    & $Python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) {
        throw "pytest failed"
    }
}

Write-Host "ci_mandatory_checks: OK"
