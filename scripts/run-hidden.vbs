Option Explicit

Dim shell, fileSystem, runnerPath, powerShellPath, command, exitCode

If WScript.Arguments.Count <> 1 Then
    WScript.Quit 64
End If

runnerPath = WScript.Arguments(0)
Set fileSystem = CreateObject("Scripting.FileSystemObject")
If Not fileSystem.FileExists(runnerPath) Then
    WScript.Quit 2
End If

Set shell = CreateObject("WScript.Shell")
powerShellPath = shell.ExpandEnvironmentStrings("%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
If Not fileSystem.FileExists(powerShellPath) Then
    WScript.Quit 2
End If

command = Chr(34) & powerShellPath & Chr(34) _
    & " -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File " _
    & Chr(34) & Replace(runnerPath, Chr(34), Chr(34) & Chr(34)) & Chr(34)

exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode
