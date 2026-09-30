# Build dist\payload for Inno Setup (Slysh.iss). Requires uv on PATH for light venv sync.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Payload = Join-Path $Root "dist\payload"
$PayloadStaging = Join-Path $Root "dist\payload.staging"
$PayloadPrev = Join-Path $Root "dist\payload.prev"
$UvVersion = "0.8.22"
$UvAsset = "uv-x86_64-pc-windows-msvc.zip"
$UvUrl = "https://github.com/astral-sh/uv/releases/download/$UvVersion/$UvAsset"

$PayloadFinal = Join-Path $Root "dist\payload"

function Resolve-FfmpegSource {
    $candidates = @(
        (Join-Path $Root "bin\ffmpeg.exe"),
        (Join-Path $PayloadFinal "bin\ffmpeg.exe")
    )
    foreach ($path in $candidates) {
        if (Test-Path -LiteralPath $path) {
            return $path
        }
    }
    throw "ffmpeg.exe not found. Put it in bin\ffmpeg.exe or keep dist\payload\bin\ffmpeg.exe from a prior build."
}

$PrebuiltExe = Join-Path $Root "installer\prebuilt\Slysh.exe"
if (-not (Test-Path -LiteralPath $PrebuiltExe)) {
    throw "Missing $PrebuiltExe. Run scripts\build-slysh-launcher.ps1 (see launcher\README.md)."
}
$null = Resolve-FfmpegSource

$LauncherScript = Join-Path $Root "scripts\build-slysh-launcher.ps1"
if (Test-Path -LiteralPath $LauncherScript) {
    Write-Host "Rebuilding Slysh.exe launcher..."
    & powershell -NoProfile -File $LauncherScript
    if ($LASTEXITCODE -ne 0) {
        throw "build-slysh-launcher.ps1 failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Building installer payload (staging: $PayloadStaging)"

if (Test-Path -LiteralPath $PayloadStaging) {
    Remove-Item -LiteralPath $PayloadStaging -Recurse -Force
}
New-Item -ItemType Directory -Path $PayloadStaging -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $PayloadStaging "bin") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $PayloadStaging "models") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $PayloadStaging "licenses") -Force | Out-Null
$Payload = $PayloadStaging

$copyNames = @(
    "src",
    "web",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    "Slysh.bat",
    "slysh.ico"
)
foreach ($name in $copyNames) {
    $src = Join-Path $Root $name
    if (-not (Test-Path -LiteralPath $src)) {
        throw "Missing $src"
    }
    Copy-Item -LiteralPath $src -Destination (Join-Path $Payload $name) -Recurse -Force
}

$pyproject = Join-Path $Root "pyproject.toml"
$pyText = Get-Content -LiteralPath $pyproject -Raw -Encoding UTF8
if ($pyText -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "Could not read version from pyproject.toml"
}
$AppVersion = $Matches[1]
$githubRepo = $env:SLYSH_GITHUB_REPO
if (-not $githubRepo) {
    $githubRepo = "dabder88/slysh"
}
$versionJson = @{
    version     = $AppVersion
    channel     = "stable"
    github_repo = $githubRepo
} | ConvertTo-Json -Compress
$versionPath = Join-Path $Payload "version.json"
[System.IO.File]::WriteAllText($versionPath, $versionJson, [System.Text.UTF8Encoding]::new($false))
Write-Host "version.json: $AppVersion ($githubRepo)"

$gitkeep = Join-Path $Root "models\.gitkeep"
if (Test-Path -LiteralPath $gitkeep) {
    Copy-Item -LiteralPath $gitkeep -Destination (Join-Path $Payload "models\.gitkeep") -Force
}

$howToDir = Join-Path $Root "installer"
$howTo = Get-ChildItem -LiteralPath $howToDir -Filter "*.txt" |
    Where-Object { $_.Name -ne "ffmpeg-LGPL.txt" } |
    Select-Object -First 1
if (-not $howTo) {
    throw "Missing user readme .txt in installer\"
}
Copy-Item -LiteralPath $howTo.FullName -Destination (Join-Path $Payload $howTo.Name) -Force

$lgpl = Join-Path $Root "installer\ffmpeg-LGPL.txt"
if (Test-Path -LiteralPath $lgpl) {
    Copy-Item -LiteralPath $lgpl -Destination (Join-Path $Payload "licenses\ffmpeg-LGPL.txt") -Force
}

$ffmpegSrc = Resolve-FfmpegSource
Copy-Item -LiteralPath $ffmpegSrc -Destination (Join-Path $Payload "bin\ffmpeg.exe") -Force

Copy-Item -LiteralPath $PrebuiltExe -Destination (Join-Path $Payload "Slysh.exe") -Force

$uvZip = Join-Path $env:TEMP "slysh-uv-$UvVersion.zip"
$uvDir = Join-Path $env:TEMP "slysh-uv-$UvVersion"
if (Test-Path -LiteralPath $uvDir) {
    Remove-Item -LiteralPath $uvDir -Recurse -Force
}
Write-Host "Downloading uv $UvVersion..."
Invoke-WebRequest -Uri $UvUrl -OutFile $uvZip -UseBasicParsing
Expand-Archive -LiteralPath $uvZip -DestinationPath $uvDir -Force
$uvExe = Get-ChildItem -LiteralPath $uvDir -Filter "uv.exe" -Recurse | Select-Object -First 1
if (-not $uvExe) {
    throw "uv.exe not found in $uvDir"
}
Copy-Item -LiteralPath $uvExe.FullName -Destination (Join-Path $Payload "bin\uv.exe") -Force

$BundledUv = Join-Path $Payload "bin\uv.exe"
$RuntimePython = Join-Path $Payload "runtime\python"
New-Item -ItemType Directory -Path $RuntimePython -Force | Out-Null
$env:UV_PYTHON_INSTALL_DIR = $RuntimePython

Push-Location $Payload
try {
    Write-Host "uv python install 3.12 (portable under runtime\python)..."
    & $BundledUv python install 3.12
    if ($LASTEXITCODE -ne 0) {
        throw "uv python install failed with exit code $LASTEXITCODE"
    }
    Write-Host "uv sync --no-editable (light UI venv)..."
    & $BundledUv sync --no-editable
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    Remove-Item Env:UV_PYTHON_INSTALL_DIR -ErrorAction SilentlyContinue
}

$Python = Join-Path $Payload ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Payload venv python missing: $Python"
}

& $Python -c "import slysh; print('slysh ok')"
if ($LASTEXITCODE -ne 0) {
    throw "slysh import failed in payload venv"
}

& $Python -c "import torch"
if ($LASTEXITCODE -eq 0) {
    throw "payload venv must not include torch before first-run extras"
}

Write-Host "Building wheelhouse for offline UI venv repair..."
$Wheelhouse = Join-Path $Payload "wheelhouse"
New-Item -ItemType Directory -Path $Wheelhouse -Force | Out-Null
$ReqExport = Join-Path $Wheelhouse "requirements-export.txt"
& $BundledUv export --frozen --no-dev --no-emit-project --no-editable --format requirements.txt -o $ReqExport
if ($LASTEXITCODE -ne 0) {
    throw "uv export for wheelhouse failed with exit code $LASTEXITCODE"
}
& $BundledUv run --directory $Payload --with pip pip download -r $ReqExport -d $Wheelhouse
if ($LASTEXITCODE -ne 0) {
    throw "pip download for wheelhouse failed with exit code $LASTEXITCODE"
}
& $BundledUv build --wheel -o $Wheelhouse
if ($LASTEXITCODE -ne 0) {
    throw "uv build wheel for slysh failed with exit code $LASTEXITCODE"
}
$whCount = (Get-ChildItem -LiteralPath $Wheelhouse -Filter "*.whl").Count
if ($whCount -lt 10) {
    throw "wheelhouse too small ($whCount wheels): $Wheelhouse"
}
Write-Host "wheelhouse: $whCount wheels"

$html = Get-Content -LiteralPath (Join-Path $Payload "web\index.html") -Raw -Encoding UTF8
foreach ($needle in @("btn-download-model", "engine-setup-settings", "btn-install-engine")) {
    if ($html -notmatch [regex]::Escape($needle)) {
        throw "web/index.html missing $needle"
    }
}

$Smoke = Join-Path $Root "scripts\smoke_installer_layout.py"
$SmokePy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $SmokePy)) {
    $SmokePy = "python"
}
& $SmokePy $Smoke
if ($LASTEXITCODE -ne 0) {
    throw "smoke_installer_layout.py failed"
}

if (Test-Path -LiteralPath $PayloadFinal) {
    if (Test-Path -LiteralPath $PayloadPrev) {
        Remove-Item -LiteralPath $PayloadPrev -Recurse -Force
    }
    Move-Item -LiteralPath $PayloadFinal -Destination $PayloadPrev
}
Move-Item -LiteralPath $PayloadStaging -Destination $PayloadFinal
$Payload = $PayloadFinal

Write-Host "Payload OK: $Payload"
if (Test-Path -LiteralPath $PayloadPrev) {
    Write-Host "Previous payload kept at: $PayloadPrev"
}
Write-Host "Next: powershell -File scripts\build-slysh-setup.ps1"
