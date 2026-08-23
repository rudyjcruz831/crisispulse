$ErrorActionPreference = "Stop"
$TaskName = "CrisisPulse Production Soak Refresh"

$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Task) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
