# F.5: scan tracked source for literal secret-like values (not env var names).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$literalPatterns = @(
    'sk-or-v1-[A-Za-z0-9]{20,}',
    'sk-proj-[A-Za-z0-9]{20,}',
    'ghp_[A-Za-z0-9]{30,}',
    'AKIA[0-9A-Z]{16}'
)

$hits = @()
foreach ($pat in $literalPatterns) {
    $match = git grep -E $pat -- src scripts ci 2>$null
    if ($match) {
        $hits += $match
    }
}

if ($hits.Count -eq 0) {
    Write-Host "audit_git_secrets: no literal API keys in tracked src/scripts/ci"
    exit 0
}

Write-Host "audit_git_secrets: REVIEW REQUIRED" -ForegroundColor Yellow
$hits | ForEach-Object { Write-Host $_ }
exit 1
