# Kill leftover Slysh / engine processes after smokes, pytest, or agent sessions.
# Does NOT stop arbitrary Python — only processes whose CommandLine matches Slysh patterns.
#
# Usage:
#   powershell -File scripts\kill_slysh_orphans.ps1           # list + confirm
#   powershell -File scripts\kill_slysh_orphans.ps1 -Force    # kill without prompt
#   powershell -File scripts\kill_slysh_orphans.ps1 -WhatIf    # list only
#
#Requires -Version 5.1
param(
    [switch]$WhatIf,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$NameFilter = "Name='python.exe' OR Name='pythonw.exe' OR Name='Slysh.exe' OR Name='cmd.exe'"

$LinePatterns = @(
    'slysh\.app'
    'slysh\.engine_server'
    '-m\s+slysh\.engine_server'
    '\\slysh\\'
    '/slysh/'
    'Slysh\.bat'
    'Slysh-Setup'
    'Slysh\.exe'
)

function Test-SlyshCommandLine {
    param([string]$CommandLine)
    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return $false
    }
    foreach ($pat in $LinePatterns) {
        if ($CommandLine -match $pat) {
            return $true
        }
    }
    return $false
}

function Get-SlyshOrphanProcesses {
    $mine = $PID
    $list = @()
    foreach ($proc in Get-CimInstance Win32_Process -Filter $NameFilter) {
        if ($proc.ProcessId -eq $mine) {
            continue
        }
        $cmd = $proc.CommandLine
        if (-not (Test-SlyshCommandLine $cmd)) {
            continue
        }
        # cmd.exe only when it is launching Slysh (avoid random cmd windows)
        if ($proc.Name -eq 'cmd.exe' -and $cmd -notmatch 'Slysh\.bat') {
            continue
        }
        $list += [pscustomobject]@{
            ProcessId   = $proc.ProcessId
            Name        = $proc.Name
            CommandLine = $cmd
        }
    }
    return $list | Sort-Object ProcessId -Unique
}

$targets = @(Get-SlyshOrphanProcesses)
if ($targets.Count -eq 0) {
    Write-Host "kill_slysh_orphans: no matching processes."
    exit 0
}

Write-Host "kill_slysh_orphans: found $($targets.Count) process(es):"
foreach ($t in $targets) {
    $short = $t.CommandLine
    if ($short.Length -gt 160) {
        $short = $short.Substring(0, 157) + "..."
    }
    Write-Host ("  PID {0,6} {1,-12} {2}" -f $t.ProcessId, $t.Name, $short)
}

if ($WhatIf) {
    Write-Host "WhatIf: no processes terminated."
    exit 0
}

if (-not $Force) {
    $answer = Read-Host "Terminate these processes? [y/N]"
    if ($answer -notmatch '^[yY]') {
        Write-Host "Cancelled."
        exit 0
    }
}

$failed = 0
foreach ($t in $targets) {
    try {
        Stop-Process -Id $t.ProcessId -Force -ErrorAction Stop
        Write-Host "  stopped PID $($t.ProcessId)"
    }
    catch {
        Write-Warning "  could not stop PID $($t.ProcessId): $($_.Exception.Message)"
        $failed++
    }
}

if ($failed -gt 0) {
    exit 1
}
Write-Host "kill_slysh_orphans: done."
exit 0
