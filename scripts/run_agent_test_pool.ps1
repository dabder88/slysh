# Scenario test pool for agent / maintainer — on demand only (not CI, not a replacement for targeted pytest).
param(
    [ValidateSet("Core", "Extended", "Live", "All")]
    [string] $Tier = "Core",
    [string[]] $ScenarioProfile = @(),
    [switch] $List
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

. (Join-Path $PSScriptRoot "agent_test_pool_manifest.ps1")

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

function Show-AgentTestPoolList {
    $profiles = Get-AgentTestPoolProfileTable
    $tiers = Get-AgentTestPoolTierTable
    Write-Host "=== Agent test pool (on demand) ==="
    Write-Host "Command: powershell -File scripts\run_agent_test_pool.ps1 [-Tier Core|Extended|Live|All] [-ScenarioProfile name ...]"
    Write-Host ""
    Write-Host "Tiers:"
    foreach ($key in @("Core", "Extended", "Live")) {
        $t = $tiers[$key]
        Write-Host "  $key — $($t.Label)"
        if ($t.Profiles) {
            Write-Host "    profiles: $($t.Profiles -join ', ')"
        }
    }
    Write-Host ""
    Write-Host "Profiles:"
    foreach ($key in ($profiles.Keys | Sort-Object)) {
        $p = $profiles[$key]
        Write-Host "  $key — $($p.Label)"
        if ($p.PyTests.Count) {
            Write-Host "    pytest: $($p.PyTests -join ', ')"
        }
        if ($p.Smokes.Count) {
            $smokeNames = ($p.Smokes | ForEach-Object { if ($_ -is [string]) { $_ } else { $_.Path } }) -join ", "
            Write-Host "    smoke: $smokeNames"
        }
    }
    Write-Host ""
    Write-Host "Guide: docs/guides/AGENT-TEST-POOL.md"
    Write-Host "Does NOT replace: ci_mandatory_checks.ps1, targeted pytest after tasks, transcription-progress rules."
}

if ($List) {
    Show-AgentTestPoolList
    exit 0
}

$resolved = Resolve-AgentTestPoolItems -Tier $Tier -ScenarioProfile $ScenarioProfile
Write-Host "=== agent test pool tier=$Tier profiles=$($resolved.ProfileNames -join ',') ==="
Write-Host "pytest files: $($resolved.PyTests.Count); smokes: $($resolved.Smokes.Count)"

$env:PYTHONPATH = "src"
$env:GIGAAM_SKIP_ENGINE = "1"
$env:GIGAAM_UI_AUTH = "0"
$env:GIGAAM_LOOPBACK_STRICT = "0"
$env:SLYSH_DISABLE_OPENAPI = "1"

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$warned = 0

foreach ($smokeEntry in $resolved.Smokes) {
    $rel = $smokeEntry
    $smokeEnv = @{}
    $warnMissingVenv = $false
    if ($smokeEntry -is [hashtable]) {
        $rel = $smokeEntry.Path
        if ($smokeEntry.Env) {
            foreach ($k in $smokeEntry.Env.Keys) {
                $smokeEnv[$k] = $smokeEntry.Env[$k]
            }
        }
        if ($smokeEntry.WarnOnMissingVenv) {
            $warnMissingVenv = $true
        }
    }

    $path = Join-Path $Root ($rel -replace "/", "\")
    if (-not (Test-Path -LiteralPath $path)) {
        throw "missing smoke: $rel"
    }

    if ($warnMissingVenv -and -not (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\python.exe"))) {
        Write-Warning "SKIP live smoke $rel (no .venv)"
        $warned++
        continue
    }

    Write-Host "--- smoke $rel ---"
    $saved = @{}
    foreach ($k in $smokeEnv.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, "Process")
        Set-Item -Path "env:$k" -Value $smokeEnv[$k]
    }
    try {
        & $Python $path
        $code = $LASTEXITCODE
    } finally {
        foreach ($k in $smokeEnv.Keys) {
            if ($null -eq $saved[$k]) {
                Remove-Item -Path "env:$k" -ErrorAction SilentlyContinue
            } else {
                Set-Item -Path "env:$k" -Value $saved[$k]
            }
        }
    }

    if ($code -ne 0 -and $warnMissingVenv) {
        Write-Warning "live smoke $rel exited $code (treated as WARN for optional Live tier)"
        $warned++
        continue
    }
    if ($code -ne 0) {
        throw "smoke failed: $rel (exit $code)"
    }
}

if ($resolved.PyTests.Count -gt 0) {
    Write-Host "--- pytest ($($resolved.PyTests.Count) files) ---"
    foreach ($rel in $resolved.PyTests) {
        $filePart = ($rel -split "::", 2)[0]
        $path = Join-Path $Root ($filePart -replace "/", "\")
        if (-not (Test-Path -LiteralPath $path)) {
            throw "missing pytest file: $filePart (from $rel)"
        }
    }
    $pyArgs = $resolved.PyTests
    & $Python -m pytest @pyArgs -q --tb=short
    if ($LASTEXITCODE -ne 0) {
        throw "pytest agent test pool failed"
    }
}

$sw.Stop()
Write-Host "agent_test_pool: OK in $([math]::Round($sw.Elapsed.TotalSeconds, 1))s (warns=$warned)"
Write-Host "Note: full CI regression remains scripts\ci_mandatory_checks.ps1"
