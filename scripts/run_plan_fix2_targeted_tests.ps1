# Targeted regressions for plan-fix-2 waves G–H (no npm / full CI).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$env:PYTHONPATH = "src"
$env:GIGAAM_SKIP_ENGINE = "1"
$env:GIGAAM_UI_AUTH = "0"
$env:GIGAAM_LOOPBACK_STRICT = "0"
$env:SLYSH_DISABLE_OPENAPI = "1"

$PyTests = @(
    "tests/test_speakers_cancel.py",
    "tests/test_chunking.py",
    "tests/test_single_instance.py",
    "tests/test_secrets_dpapi_migration.py",
    "tests/test_loopback_security.py",
    "tests/test_engine_client_timeout.py",
    "tests/test_engine_watchdog.py",
    "tests/test_engine_cancel.py",
    "tests/test_updates_operation.py",
    "tests/test_updates_redirect.py",
    "tests/test_updates_sha.py",
    "tests/test_offline_bootstrap.py",
    "tests/test_job_asr_snapshot.py",
    "tests/test_gemini_cli.py",
    "tests/test_decode_cancel.py",
    "tests/test_webview2_redist.py"
)

Write-Host "=== smoke_cloud_batch_route ==="
& $Python (Join-Path $Root "scripts\smoke_cloud_batch_route.py")
if ($LASTEXITCODE -ne 0) {
    throw "smoke_cloud_batch_route failed"
}

Write-Host "=== pytest plan-fix-2 subset ==="
& $Python -m pytest @PyTests -q --tb=short
if ($LASTEXITCODE -ne 0) {
    throw "pytest plan-fix-2 subset failed"
}

Write-Host "run_plan_fix2_targeted_tests: OK"
