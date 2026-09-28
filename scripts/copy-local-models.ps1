# Copy ASR weights into this app's models folder. Skip a destination if it already exists.
# Does not create junctions. Runtime never reads Buzz or other Hugging Face caches.

$ErrorActionPreference = "Stop"
$dstRoot = Join-Path (Split-Path -Parent $PSScriptRoot) "models"
$buzzModels = $env:SLYSH_BUZZ_MODELS
$buzzWhisper = Join-Path $env:LOCALAPPDATA "Buzz\Buzz\Cache\models\whisper"
$hfHub = Join-Path $env:USERPROFILE ".cache\huggingface\hub"

New-Item -ItemType Directory -Force -Path $dstRoot | Out-Null

function Copy-DirIfMissing {
    param(
        [Parameter(Mandatory = $true)][string]$From,
        [Parameter(Mandatory = $true)][string]$To
    )
    if (-not (Test-Path -LiteralPath $From)) {
        Write-Host "Skip missing source: $From"
        return
    }
    if (Test-Path -LiteralPath $To) {
        Write-Host "Already present: $To"
        return
    }
    Write-Host "Copy $From -> $To"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $To) | Out-Null
    & robocopy $From $To /E /NFL /NDL /NJH /NJS /nc /ns /np
    $code = $LASTEXITCODE
    if ($code -ge 8) {
        Write-Error "robocopy failed ($code): $From"
    }
}

function Copy-FileIfMissing {
    param(
        [Parameter(Mandatory = $true)][string]$From,
        [Parameter(Mandatory = $true)][string]$To
    )
    if (-not (Test-Path -LiteralPath $From)) {
        Write-Host "Skip missing source: $From"
        return
    }
    if (Test-Path -LiteralPath $To) {
        Write-Host "Already present: $To"
        return
    }
    Write-Host "Copy file $From"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $To) | Out-Null
    Copy-Item -LiteralPath $From -Destination $To
}

if ($buzzModels -and (Test-Path -LiteralPath $buzzModels)) {
    Copy-DirIfMissing -From (Join-Path $buzzModels "gigaam") -To (Join-Path $dstRoot "gigaam")
    Get-ChildItem -LiteralPath $buzzModels -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $name = $_.Name
        if ($name -like "models--Systran--faster-whisper-*" -or
            $name -eq "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo") {
            Copy-DirIfMissing -From $_.FullName -To (Join-Path $dstRoot $name)
        }
    }
}
else {
    Write-Host "Skip missing source: $buzzModels"
}

if (Test-Path -LiteralPath $buzzWhisper) {
    Get-ChildItem -LiteralPath $buzzWhisper -File -Filter "*.pt" | ForEach-Object {
        Copy-FileIfMissing -From $_.FullName -To (Join-Path $dstRoot "whisper\$($_.Name)")
    }
}
else {
    Write-Host "Skip missing source: $buzzWhisper"
}

if (Test-Path -LiteralPath $hfHub) {
    Get-ChildItem -LiteralPath $hfHub -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $name = $_.Name
        if ($name -like "models--Systran--faster-whisper-*" -or
            $name -eq "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo") {
            Copy-DirIfMissing -From $_.FullName -To (Join-Path $dstRoot $name)
        }
    }
}

Write-Host "Done. Models folder: $dstRoot"
