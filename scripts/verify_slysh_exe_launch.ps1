# Quick launch verification for dist/payload/Slysh.exe (plan checklist B1-B3).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$PayloadDir = Join-Path $Root "dist\payload"
$Exe = Join-Path $PayloadDir "Slysh.exe"

if (-not (Test-Path -LiteralPath $Exe)) {
    Write-Error "Missing $Exe. Run build-installer-payload.ps1 first."
}

$beforeCmd = @(Get-Process -Name cmd -ErrorAction SilentlyContinue).Count
$proc = Start-Process -FilePath $Exe -WorkingDirectory $PayloadDir -PassThru
Start-Sleep -Seconds 18

$pythonw = Get-Process -Name pythonw -ErrorAction SilentlyContinue
$slysh = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
$afterCmd = @(Get-Process -Name cmd -ErrorAction SilentlyContinue).Count

$ok = $true
if (-not $pythonw) {
    Write-Host "FAIL: pythonw process not found after 18s"
    $ok = $false
} else {
    Write-Host "PASS: pythonw running (PID $($pythonw[0].Id))"
}
if ($afterCmd -gt $beforeCmd) {
    Write-Host ('WARN: cmd.exe count increased ({0} -> {1})' -f $beforeCmd, $afterCmd)
} else {
    Write-Host "PASS: no new cmd.exe processes"
}
if ($slysh) {
    Write-Host "INFO: Slysh.exe still waiting on child (PID $($proc.Id))"
}

foreach ($p in $pythonw) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
if ($slysh) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

if (-not $ok) { exit 1 }
Write-Host "verify_slysh_exe_launch: OK"
