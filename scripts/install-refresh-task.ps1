param(
    [string]$TaskName = "CrisisPulse Refresh",
    [ValidateRange(15, 1440)]
    [int]$IntervalMinutes = 15,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

$RefreshScript = (Resolve-Path (Join-Path $PSScriptRoot "run-refresh.ps1")).Path
$ActionArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$RefreshScript`""
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $ActionArguments
$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes ([Math]::Max($IntervalMinutes - 1, 14)))

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Refreshes the local CrisisPulse GDELT pipeline and dashboard snapshot." `
    -Force | Out-Null

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
}

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
