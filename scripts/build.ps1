param(
    [string]$Python = "python",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $SkipInstall) {
    & $Python -m pip install -r requirements.txt -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $Python tools/build_icon.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m PyInstaller --noconfirm --clean StudyPet.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Built: $root\dist\StudyPet\StudyPet.exe"
