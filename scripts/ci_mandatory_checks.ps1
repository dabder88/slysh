# Wave F: mandatory checks (prod-launch CI + maintainer), including pytest when tests/ exists.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Host "=== check-web-js ==="
powershell -NoProfile -File (Join-Path $Root "scripts\check-web-js.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "check-web-js.ps1 failed"
}

Write-Host "=== build:css ==="
npm ci
if ($LASTEXITCODE -ne 0) {
    throw "npm ci failed"
}
npm run build:css
if ($LASTEXITCODE -ne 0) {
    throw "npm run build:css failed"
}

Write-Host "=== ci/check_import_path.py ==="
& $Python (Join-Path $Root "ci\check_import_path.py")
if ($LASTEXITCODE -ne 0) {
    throw "ci/check_import_path.py failed"
}

Write-Host "=== ci/check_ui_imports.py ==="
& $Python (Join-Path $Root "ci\check_ui_imports.py")
if ($LASTEXITCODE -ne 0) {
    throw "ci/check_ui_imports.py failed"
}

Write-Host "=== ci/check_gemini_cli_prompt.py ==="
& $Python (Join-Path $Root "ci\check_gemini_cli_prompt.py")
if ($LASTEXITCODE -ne 0) {
    throw "ci/check_gemini_cli_prompt.py failed"
}

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
    "scripts\smoke_runtime_env_slots.py",
    "scripts\smoke_engine_slot_resync.py",
    "scripts\smoke_cloud_batch_route.py"
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

Write-Host "=== run_plan_fix3_gate (targeted + full pytest) ==="
powershell -NoProfile -File (Join-Path $Root "scripts\run_plan_fix3_gate.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "run_plan_fix3_gate.ps1 failed"
}

Write-Host "ci_mandatory_checks: OK"
