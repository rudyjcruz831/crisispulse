$ErrorActionPreference = "Stop"
$TaskName = "CrisisPulse Production Backup"

$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $Task) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Removed scheduled task: $TaskName"
}
else {
    Write-Output "Scheduled task not installed: $TaskName"
}
