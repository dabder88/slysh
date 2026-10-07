# plan-fix-3 I8 (R15): JS syntax + targeted F2/F3 regressions (mandatory).
# Optional: SLYSH_GATE_FULL_PYTEST=1 — full tests/ (no WebView2 shell file; no PyPI wheel fixture).
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

Write-Host "=== check-web-js ==="
powershell -NoProfile -File (Join-Path $Root "scripts\check-web-js.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "check-web-js.ps1 failed"
}

Write-Host "=== run_plan_fix2_targeted_tests (plan-fix-2 + fix-3 subset) ==="
powershell -NoProfile -File (Join-Path $Root "scripts\run_plan_fix2_targeted_tests.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "run_plan_fix2_targeted_tests.ps1 failed"
}

if ($env:SLYSH_GATE_FULL_PYTEST -ne "1") {
    Write-Host "run_plan_fix3_gate: OK (full pytest skipped; set SLYSH_GATE_FULL_PYTEST=1 to run)"
    exit 0
}

$BasetempRoot = Join-Path $env:TEMP ("slysh-pytest-basetemp-" + [guid]::NewGuid().ToString("n"))
New-Item -ItemType Directory -Force -Path $BasetempRoot | Out-Null
$env:SLYSH_PYTEST_GATE = "1"

try {
    Write-Host "=== pytest full suite (optional; ignores test_webview2.py) ==="
    & $Python -m pytest tests -q --tb=line --basetemp $BasetempRoot --ignore=tests/test_webview2.py
    if ($LASTEXITCODE -ne 0) {
        throw "full pytest failed"
    }
}
finally {
    Remove-Item Env:SLYSH_PYTEST_GATE -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $BasetempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "run_plan_fix3_gate: OK (with full pytest)"
