# Download installer/redist assets (WebView2 bootstrapper + optional offline standalone).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Redist = Join-Path $Root "installer\redist"
$BootstrapperUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
$BootstrapperDest = Join-Path $Redist "MicrosoftEdgeWebview2Setup.exe"
$StandaloneDest = Join-Path $Redist "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
$StandaloneUrlFile = Join-Path $Redist "webview2-standalone.url"
$MinBootstrapper = 65536
$MinStandalone = 40 * 1024 * 1024

New-Item -ItemType Directory -Path $Redist -Force | Out-Null

function Test-PeExe {
    param([string]$Path, [int]$MinBytes)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $len = (Get-Item -LiteralPath $Path).Length
    if ($len -lt $MinBytes) { return $false }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    return ($bytes.Length -ge 2 -and $bytes[0] -eq 0x4D -and $bytes[1] -eq 0x5A)
}

function Ensure-Bootstrapper {
    if (Test-PeExe -Path $BootstrapperDest -MinBytes $MinBootstrapper) {
        $len = (Get-Item -LiteralPath $BootstrapperDest).Length
        if ($len -lt $MinStandalone) {
            Write-Host "WebView2 bootstrapper OK: $BootstrapperDest ($len bytes)"
            return
        }
        Write-Warning "Bootstrapper file too large (standalone?): $BootstrapperDest"
    }
    Write-Host "Downloading WebView2 bootstrapper..."
    Invoke-WebRequest -Uri $BootstrapperUrl -OutFile $BootstrapperDest -UseBasicParsing
    if (-not (Test-PeExe -Path $BootstrapperDest -MinBytes $MinBootstrapper)) {
        throw "Downloaded file does not look like WebView2 bootstrapper: $BootstrapperDest"
    }
    Write-Host "Saved bootstrapper: $BootstrapperDest"
}

function Resolve-StandaloneUrl {
    $fromEnv = $env:SLYSH_WEBVIEW2_STANDALONE_URL
    if ($fromEnv) { return $fromEnv.Trim() }
    if (Test-Path -LiteralPath $StandaloneUrlFile) {
        $line = (Get-Content -LiteralPath $StandaloneUrlFile -ErrorAction Stop | Select-Object -First 1)
        if ($line) { return $line.Trim() }
    }
    return $null
}

function Ensure-Standalone {
    if (Test-PeExe -Path $StandaloneDest -MinBytes $MinStandalone) {
        $len = (Get-Item -LiteralPath $StandaloneDest).Length
        Write-Host "WebView2 standalone installer OK: $StandaloneDest ($len bytes)"
        return
    }
    $standaloneUrl = Resolve-StandaloneUrl
    if (-not $standaloneUrl) {
        Write-Warning @"
WebView2 offline standalone not configured.
Copy Evergreen Standalone Installer x64 to:
  $StandaloneDest
or set installer\redist\webview2-standalone.url (one https URL per line) or env SLYSH_WEBVIEW2_STANDALONE_URL.
Setup will use the online bootstrapper until standalone is present.
"@
        return
    }
    Write-Host "Downloading WebView2 standalone installer..."
    Invoke-WebRequest -Uri $standaloneUrl -OutFile $StandaloneDest -UseBasicParsing
    if (-not (Test-PeExe -Path $StandaloneDest -MinBytes $MinStandalone)) {
        Remove-Item -LiteralPath $StandaloneDest -Force -ErrorAction SilentlyContinue
        throw "Downloaded file does not look like WebView2 standalone installer: $StandaloneDest"
    }
    Write-Host "Saved standalone: $StandaloneDest ($((Get-Item -LiteralPath $StandaloneDest).Length) bytes)"
}

Ensure-Bootstrapper
Ensure-Standalone
