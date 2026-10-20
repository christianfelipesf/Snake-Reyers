param(
    [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
} else {
    $RootDir = (Resolve-Path $InstallRoot).Path
}

$Launcher = Join-Path $RootDir "launcher\start_windows.vbs"
$GameExe = Join-Path $RootDir "game\windows\SnakeReyers.exe"
$DesktopDir = [Environment]::GetFolderPath("Desktop")

if (-not (Test-Path $Launcher -PathType Leaf)) {
    throw "Iniciador do Windows nao encontrado: $Launcher"
}
if (-not (Test-Path $GameExe -PathType Leaf)) {
    throw "Executavel usado pelo icone nao encontrado: $GameExe"
}
if ([string]::IsNullOrWhiteSpace($DesktopDir)) {
    $DesktopDir = Join-Path $env:USERPROFILE "Desktop"
}

New-Item -ItemType Directory -Force -Path $DesktopDir | Out-Null

$LegacyShortcut = Join-Path $DesktopDir "Snake Reyers.lnk"
if (Test-Path $LegacyShortcut -PathType Leaf) {
    Remove-Item -LiteralPath $LegacyShortcut -Force -ErrorAction SilentlyContinue
}

$ShortcutPath = Join-Path $DesktopDir "Snake Reyers Lite.lnk"
$WScript = Join-Path $env:SystemRoot "System32\wscript.exe"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $WScript
$Shortcut.Arguments = "`"$Launcher`""
$Shortcut.WorkingDirectory = $RootDir
$Shortcut.IconLocation = "$GameExe,0"
$Shortcut.Description = "Iniciar o Snake Reyers Lite e abrir o painel"
$Shortcut.Save()

Write-Host "Atalho criado na Area de Trabalho: $ShortcutPath"
