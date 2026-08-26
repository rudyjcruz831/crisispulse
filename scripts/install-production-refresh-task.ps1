param(
    [ValidateRange(5, 60)]
    [int]$IntervalMinutes = 15
)

$ErrorActionPreference = "Stop"
$TaskName = "CrisisPulse Production Refresh"
$ExpiredSoakTaskName = "CrisisPulse Production Soak Refresh"
$Runner = Join-Path $PSScriptRoot "run-production-refresh.ps1"
$HiddenLauncher = Join-Path $PSScriptRoot "run-hidden.vbs"
$WScript = Join-Path $env:SystemRoot "System32\wscript.exe"
if (-not (Test-Path -LiteralPath $Runner) -or -not (Test-Path -LiteralPath $HiddenLauncher)) {
    throw "The production refresh runner or hidden launcher is missing."
}
if (-not (Test-Path -LiteralPath $WScript)) {
    throw "Windows Script Host is missing."
}

$StartAt = (Get-Date).AddMinutes(1)
$Action = New-ScheduledTaskAction `
    -Execute $WScript `
    -Argument "//B //NoLogo `"$HiddenLauncher`" `"$Runner`""
# Leaving RepetitionDuration empty tells Task Scheduler to repeat indefinitely.
$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $StartAt `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 14) `
    -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description "Runs the local Docker production refresh every $IntervalMinutes minutes until explicitly removed." `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Force | Out-Null

if (Get-ScheduledTask -TaskName $ExpiredSoakTaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $ExpiredSoakTaskName -Confirm:$false
}

$Task = Get-ScheduledTask -TaskName $TaskName
$TaskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{
    task_name = $TaskName
    state = $Task.State.ToString()
    starts_at = $StartAt.ToUniversalTime().ToString("o")
    next_run_at = $TaskInfo.NextRunTime.ToUniversalTime().ToString("o")
    interval_minutes = $IntervalMinutes
    repeats_indefinitely = $true
}
