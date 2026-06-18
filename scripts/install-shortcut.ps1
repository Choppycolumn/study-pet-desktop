param(
    [string]$Executable,
    [switch]$StartWithWindows
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $Executable) {
    $Executable = Join-Path $root "dist\StudyPet\StudyPet.exe"
}
$Executable = (Resolve-Path -LiteralPath $Executable).Path

function New-StudyPetShortcut([string]$Path) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Executable
    $shortcut.WorkingDirectory = Split-Path -Parent $Executable
    $shortcut.IconLocation = "$Executable,0"
    $shortcut.Description = "Windows Study Pet"
    $shortcut.Save()
}

$shortcutName = (-join ([char[]]@(0x684C, 0x5BA0, 0x81EA, 0x5F8B, 0x52A9, 0x624B))) + ".lnk"
$desktop = [Environment]::GetFolderPath("Desktop")
$desktopShortcut = Join-Path $desktop $shortcutName
New-StudyPetShortcut $desktopShortcut
Write-Host "Created: $desktopShortcut"

if ($StartWithWindows) {
    $startup = [Environment]::GetFolderPath("Startup")
    $startupShortcut = Join-Path $startup $shortcutName
    New-StudyPetShortcut $startupShortcut
    Write-Host "Created startup shortcut: $startupShortcut"
}
