# Syntax-check all ES modules under web/js (node --check).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$JsDir = Join-Path $Root "web\js"
$files = Get-ChildItem -LiteralPath $JsDir -Filter "*.js" -File | Sort-Object Name
foreach ($file in $files) {
    Write-Host "check $($file.Name)"
    & node --check $file.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "JS syntax error in $($file.FullName)"
    }
}
Write-Host "web/js: $($files.Count) files OK"
