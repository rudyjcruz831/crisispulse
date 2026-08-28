param(
    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "backup-encryption-common.ps1")

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Get-CrisisPulseDefaultEncryptionConfigPath
}
$StatusPath = Join-Path (Split-Path -Parent $ConfigPath) "encrypted-backup-status.json"
$Mutex = New-Object System.Threading.Mutex($false, "Local\CrisisPulseEncryptedBackup")
$OwnsMutex = $false

function Start-CrisisPulseOneDriveQuietly {
    if (Get-Process -Name "OneDrive" -ErrorAction SilentlyContinue) {
        return $true
    }
    $Candidates = @(
        (Join-Path $env:ProgramFiles "Microsoft OneDrive\OneDrive.exe"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\OneDrive\OneDrive.exe")
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            Start-Process -FilePath $Candidate -ArgumentList "/background" -WindowStyle Hidden
            Start-Sleep -Seconds 2
            return [bool](Get-Process -Name "OneDrive" -ErrorAction SilentlyContinue)
        }
    }
    return $false
}

try {
    $OwnsMutex = $Mutex.WaitOne(0)
    if (-not $OwnsMutex) {
        throw "Another encrypted backup is already running."
    }
    $Config = Get-CrisisPulseEncryptionConfig -ConfigPath $ConfigPath
    [byte[]]$AuthenticationKey = Get-CrisisPulseAuthenticationKeyForCurrentUser -Config $Config
    $VerifiedBackup = Get-CrisisPulseVerifiedLocalBackup `
        -BackupDirectory ([string]$Config.local_backup_directory)
    $OneDriveRunning = Start-CrisisPulseOneDriveQuietly
    $Encrypted = Protect-CrisisPulseVerifiedBackup `
        -VerifiedBackup $VerifiedBackup `
        -DestinationDirectory ([string]$Config.offsite_directory) `
        -CertificateThumbprint ([string]$Config.certificate_thumbprint) `
        -AuthenticationKey $AuthenticationKey `
        -MaxArchiveBytes ([int64]$Config.max_archive_bytes)

    $Status = [ordered]@{
        schema_version = 1
        status = "verified"
        verified_at_utc = [DateTime]::UtcNow.ToString("o")
        archive_name = $Encrypted.ArchiveName
        archive_bytes = [int64]$Encrypted.ArchiveBytes
        checksum = $Encrypted.Checksum
        encrypted_file = Split-Path -Leaf $Encrypted.EncryptedPath
        encrypted_bytes = [int64]$Encrypted.EncryptedBytes
        publication = $Encrypted.Publication
        onedrive_process_running = $OneDriveRunning
        cloud_visibility_confirmed = $false
    }
    Write-CrisisPulseUtf8Atomic `
        -Path $StatusPath `
        -Content ($Status | ConvertTo-Json)
    [pscustomobject]@{
        status = "verified"
        archive = $Encrypted.ArchiveName
        encrypted_file = $Status.encrypted_file
        publication = $Encrypted.Publication
        onedrive_process_running = $OneDriveRunning
        cloud_visibility_confirmed = $false
    }
    exit 0
}
catch {
    $Failure = [ordered]@{
        schema_version = 1
        status = "failed"
        failed_at_utc = [DateTime]::UtcNow.ToString("o")
        message = $_.Exception.Message
    }
    try {
        Write-CrisisPulseUtf8Atomic `
            -Path $StatusPath `
            -Content ($Failure | ConvertTo-Json)
    }
    catch {
        # Preserve the original failure when even the local status cannot write.
    }
    Write-Error $Failure.message
    exit 1
}
finally {
    if ($OwnsMutex) {
        $Mutex.ReleaseMutex()
    }
    $Mutex.Dispose()
}
