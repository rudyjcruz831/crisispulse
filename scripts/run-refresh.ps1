param(
    [string]$RawDir = "$env:USERPROFILE\.crisispulse\raw",
    [ValidateRange(1, 672)]
    [int]$WindowIntervals = 8,
    [ValidateRange(8, 10000)]
    [int]$RetentionFiles = 672,
    [ValidateRange(1, 16)]
    [int]$Workers = 8,
    [string]$DashboardOutput = "$env:USERPROFILE\.crisispulse\dashboard.json",
    [string]$StatusPath = "$env:USERPROFILE\.crisispulse\refresh-status.json"
)

$ErrorActionPreference = "Stop"

if ($RetentionFiles -lt $WindowIntervals) {
    throw "RetentionFiles must be at least WindowIntervals."
}

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "The local environment is missing. Run scripts\setup.ps1 first."
}

$StateRoot = Split-Path -Parent $StatusPath
New-Item -ItemType Directory -Path $StateRoot, $RawDir -Force | Out-Null
$LockPath = Join-Path $StateRoot "refresh.lock"
$LockStream = $null
try {
    $LockStream = [IO.File]::Open(
        $LockPath,
        [IO.FileMode]::OpenOrCreate,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::None
    )
}
catch [IO.IOException] {
    Write-Output '{"status":"skipped","message":"another refresh is already running"}'
    exit 0
}

$StartedAt = (Get-Date).ToUniversalTime()
$PreviousSuccess = $null
if (Test-Path -LiteralPath $StatusPath) {
    try {
        $PreviousStatus = Get-Content -LiteralPath $StatusPath -Raw | ConvertFrom-Json
        $PreviousSuccess = $PreviousStatus.last_success_at
    }
    catch {
        $PreviousSuccess = $null
    }
}

function Write-RefreshStatus {
    param(
        [string]$Status,
        [string]$Message,
        [hashtable]$Details = @{}
    )

    $FinishedAt = if ($Status -eq "running") { $null } else { (Get-Date).ToUniversalTime().ToString("o") }
    $LastSuccessAt = if ($Status -eq "success") { $FinishedAt } else { $PreviousSuccess }
    $Payload = [ordered]@{
        status = $Status
        started_at = $StartedAt.ToString("o")
        finished_at = $FinishedAt
        last_success_at = $LastSuccessAt
        message = $Message
        details = $Details
    }

    $TemporaryStatus = "$StatusPath.$PID.partial"
    $Payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $TemporaryStatus -Encoding UTF8
    Move-Item -LiteralPath $TemporaryStatus -Destination $StatusPath -Force
}

$TemporaryInput = Join-Path ([IO.Path]::GetTempPath()) ("crisispulse-refresh-" + [guid]::NewGuid().ToString("N"))
Write-RefreshStatus -Status "running" -Message "refresh started"

Push-Location $RepositoryRoot
try {
    $DownloadOutput = & $Python -m pipelines.download_history `
        --output-dir $RawDir `
        --intervals $WindowIntervals `
        --workers $Workers `
        --progress-every 0 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($DownloadOutput -join [Environment]::NewLine)
    }
    $DownloadSummary = ($DownloadOutput -join [Environment]::NewLine) | ConvertFrom-Json

    $WindowFiles = @(
        Get-ChildItem -LiteralPath $RawDir -File -Filter "*.gkg.csv.zip" |
            Sort-Object Name -Descending |
            Select-Object -First $WindowIntervals |
            Sort-Object Name
    )
    if ($WindowFiles.Count -lt $WindowIntervals) {
        throw "Only $($WindowFiles.Count) raw files are available; $WindowIntervals are required."
    }

    $FirstHourBoundary = $null
    for ($Index = 0; $Index -lt $WindowFiles.Count; $Index++) {
        $Timestamp = [datetime]::ParseExact(
            $WindowFiles[$Index].Name.Substring(0, 14),
            "yyyyMMddHHmmss",
            [Globalization.CultureInfo]::InvariantCulture
        )
        if ($Timestamp.Minute -eq 0) {
            $FirstHourBoundary = $Index
            break
        }
    }
    if ($null -eq $FirstHourBoundary) {
        throw "The downloaded window does not contain an hour boundary."
    }
    $ProcessingFiles = @($WindowFiles[$FirstHourBoundary..($WindowFiles.Count - 1)])

    New-Item -ItemType Directory -Path $TemporaryInput -Force | Out-Null
    foreach ($WindowFile in $ProcessingFiles) {
        Copy-Item -LiteralPath $WindowFile.FullName -Destination $TemporaryInput
    }

    & powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-batch.ps1 `
        -InputDir $TemporaryInput `
        -Pattern "*.gkg.csv.zip"
    if ($LASTEXITCODE -ne 0) { throw "batch processing failed with exit code $LASTEXITCODE" }

    & powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\update-history.ps1 `
        -DashboardOutput $DashboardOutput
    if ($LASTEXITCODE -ne 0) { throw "history update failed with exit code $LASTEXITCODE" }

    $PrunableFiles = @(
        Get-ChildItem -LiteralPath $RawDir -File -Filter "*.gkg.csv.zip" |
            Sort-Object Name -Descending |
            Select-Object -Skip $RetentionFiles
    )
    foreach ($PrunableFile in $PrunableFiles) {
        Remove-Item -LiteralPath $PrunableFile.FullName -Force
    }

    $RetainedFiles = @(
        Get-ChildItem -LiteralPath $RawDir -File -Filter "*.gkg.csv.zip"
    ).Count
    Write-RefreshStatus -Status "success" -Message "refresh completed" -Details @{
        downloaded_files = $DownloadSummary.downloaded_files
        already_present_files = $DownloadSummary.already_present_files
        first_file = $DownloadSummary.first_file
        last_file = $DownloadSummary.last_file
        processed_files = $ProcessingFiles.Count
        retained_raw_files = $RetainedFiles
        pruned_raw_files = $PrunableFiles.Count
        dashboard_output = $DashboardOutput
    }
}
catch {
    Write-RefreshStatus -Status "failed" -Message $_.Exception.Message
    throw
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $TemporaryInput) {
        Remove-Item -LiteralPath $TemporaryInput -Recurse -Force
    }
    if ($LockStream) {
        $LockStream.Dispose()
    }
}
