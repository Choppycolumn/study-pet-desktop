param(
    [string]$Version = "dev"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "dist\StudyPet"
if (-not (Test-Path -LiteralPath (Join-Path $source "StudyPet.exe"))) {
    throw "Build StudyPet before packaging a release."
}

$artifacts = Join-Path $root "artifacts"
New-Item -ItemType Directory -Path $artifacts -Force | Out-Null
$archive = Join-Path $artifacts "StudyPet-windows-x64-$Version.zip"
Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $source "*") -DestinationPath $archive -CompressionLevel Optimal
Write-Host "Packaged: $archive"
