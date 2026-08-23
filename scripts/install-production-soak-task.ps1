param(
    [ValidateRange(1, 168)]
    [int]$DurationHours = 48,
    [ValidateRange(5, 60)]
    [int]$IntervalMinutes = 15
)

$ErrorActionPreference = "Stop"
$TaskName = "CrisisPulse Production Soak Refresh"
$Runner = Join-Path $PSScriptRoot "run-production-refresh.ps1"
if (-not (Test-Path -LiteralPath $Runner)) {
    throw "The production refresh runner is missing."
}

$StartAt = (Get-Date).AddMinutes(1)
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`""
$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $StartAt `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Hours $DurationHours)
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 14) `
    -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description "Runs the local Docker production refresh every $IntervalMinutes minutes for a $DurationHours-hour soak test." `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Force | Out-Null

[pscustomobject]@{
    task_name = $TaskName
    starts_at = $StartAt.ToUniversalTime().ToString("o")
    ends_at = $StartAt.AddHours($DurationHours).ToUniversalTime().ToString("o")
    interval_minutes = $IntervalMinutes
}
