param(
    [ValidateRange(0, 23)]
    [int]$UtcHour = 7,

    [ValidateRange(0, 59)]
    [int]$UtcMinute = 10
)

$ErrorActionPreference = "Stop"
$TaskName = "CrisisPulse Production Backup"
$Runner = Join-Path $PSScriptRoot "run-production-backup.ps1"
$HiddenLauncher = Join-Path $PSScriptRoot "run-hidden.vbs"
$WScript = Join-Path $env:SystemRoot "System32\wscript.exe"
if (-not (Test-Path -LiteralPath $Runner) -or -not (Test-Path -LiteralPath $HiddenLauncher)) {
    throw "The production backup runner or hidden launcher is missing."
}
if (-not (Test-Path -LiteralPath $WScript)) {
    throw "Windows Script Host is missing."
}

$NowUtc = [DateTime]::UtcNow
$StartUtc = [DateTime]::SpecifyKind(
    $NowUtc.Date.AddHours($UtcHour).AddMinutes($UtcMinute),
    [DateTimeKind]::Utc
)
if ($StartUtc -le $NowUtc) {
    $StartUtc = $StartUtc.AddDays(1)
}
$StartAt = $StartUtc.ToLocalTime()

$Action = New-ScheduledTaskAction `
    -Execute $WScript `
    -Argument "//B //NoLogo `"$HiddenLauncher`" `"$Runner`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $StartAt
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 40) `
    -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description "Creates and verifies a CrisisPulse backup every day at the configured UTC time." `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Force | Out-Null

$Task = Get-ScheduledTask -TaskName $TaskName
$TaskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
$NextRunUtc = $TaskInfo.NextRunTime.ToUniversalTime()
$EasternZone = [System.TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
$NextRunEastern = [System.TimeZoneInfo]::ConvertTimeFromUtc($NextRunUtc, $EasternZone)
[pscustomobject]@{
    task_name = $TaskName
    state = $Task.State.ToString()
    next_run_at_utc = $NextRunUtc.ToString("o")
    next_run_at_eastern = $NextRunEastern.ToString("yyyy-MM-ddTHH:mm:ss")
    utc_time = "{0:D2}:{1:D2}" -f $UtcHour, $UtcMinute
    starts_when_available = $true
}
