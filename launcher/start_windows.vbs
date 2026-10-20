Option Explicit

Dim shell, fileSystem, launcherDir, startScript, command
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

launcherDir = fileSystem.GetParentFolderName(WScript.ScriptFullName)
startScript = fileSystem.BuildPath(launcherDir, "start_windows.ps1")
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " _
    & Chr(34) & startScript & Chr(34)

shell.Run command, 0, False
