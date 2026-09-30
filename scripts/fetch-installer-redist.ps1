# Download installer/redist assets (WebView2 Evergreen Bootstrapper).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Redist = Join-Path $Root "installer\redist"
$WebView2Url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
$WebView2Dest = Join-Path $Redist "MicrosoftEdgeWebview2Setup.exe"

New-Item -ItemType Directory -Path $Redist -Force | Out-Null

if (Test-Path -LiteralPath $WebView2Dest) {
    $len = (Get-Item -LiteralPath $WebView2Dest).Length
    if ($len -ge 65536) {
        Write-Host "WebView2 bootstrapper OK: $WebView2Dest ($len bytes)"
        exit 0
    }
    Remove-Item -LiteralPath $WebView2Dest -Force
}

Write-Host "Downloading WebView2 bootstrapper..."
Invoke-WebRequest -Uri $WebView2Url -OutFile $WebView2Dest -UseBasicParsing
$bytes = [System.IO.File]::ReadAllBytes($WebView2Dest)
if ($bytes.Length -lt 65536 -or $bytes[0] -ne 0x4D -or $bytes[1] -ne 0x5A) {
    throw "Downloaded file does not look like WebView2 bootstrapper: $WebView2Dest"
}
Write-Host "Saved: $WebView2Dest ($($bytes.Length) bytes)"
