param(
    [Parameter(Mandatory = $true)]
    [string]$EncryptedBackupPath,

    [string]$RecoveryBundlePath = "",

    [string]$DestinationDirectory = "",

    [securestring]$RecoveryPassword,

    [securestring]$RecoveryAuthenticationKey
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "backup-encryption-common.ps1")

if ([string]::IsNullOrWhiteSpace($RecoveryBundlePath)) {
    $RecoveryBundlePath = Join-Path `
        (Split-Path -Parent $EncryptedBackupPath) `
        "Recovery\CrisisPulse-Backup-Recovery.pfx"
}
if ([string]::IsNullOrWhiteSpace($DestinationDirectory)) {
    $DestinationDirectory = Join-Path $env:USERPROFILE "Downloads\CrisisPulse Restored Backups"
}
if (-not $RecoveryPassword) {
    $RecoveryPassword = Read-Host "Enter the CrisisPulse recovery password" -AsSecureString
}
if (-not $RecoveryAuthenticationKey) {
    $RecoveryAuthenticationKey = Read-Host "Enter the CrisisPulse recovery authentication key" -AsSecureString
}
[byte[]]$AuthenticationKey = ConvertFrom-CrisisPulseRecoveryAuthenticationKey `
    -AuthenticationKey $RecoveryAuthenticationKey

$Decrypted = Read-CrisisPulseEncryptedBackup `
    -EncryptedBackupPath $EncryptedBackupPath `
    -AuthenticationKey $AuthenticationKey `
    -RecoveryBundlePath $RecoveryBundlePath `
    -RecoveryPassword $RecoveryPassword

if (-not (Test-Path -LiteralPath $DestinationDirectory)) {
    New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
}
$Destination = Join-Path $DestinationDirectory ([string]$Decrypted.Manifest.archive_name)
if (Test-Path -LiteralPath $Destination) {
    throw "The restored archive already exists. Choose a different destination instead of overwriting it."
}
$Temporary = "$Destination.partial.$PID.$([Guid]::NewGuid().ToString('N'))"
try {
    [System.IO.File]::WriteAllBytes($Temporary, [byte[]]$Decrypted.Bytes)
    $WrittenChecksum = (Get-FileHash -LiteralPath $Temporary -Algorithm SHA256).Hash.ToLowerInvariant()
    if (
        (Get-Item -LiteralPath $Temporary).Length -ne [int64]$Decrypted.Manifest.archive_bytes -or
        $WrittenChecksum -ne [string]$Decrypted.Manifest.sha256
    ) {
        throw "The restored archive failed its final checksum verification."
    }
    & tar.exe -tzf $Temporary | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "The restored archive failed its tar integrity check."
    }
    Move-Item -LiteralPath $Temporary -Destination $Destination
}
finally {
    if (Test-Path -LiteralPath $Temporary) {
        Remove-Item -LiteralPath $Temporary -Force
    }
}

[pscustomobject]@{
    status = "verified"
    restored_archive = $Destination
    archive_bytes = [int64]$Decrypted.Manifest.archive_bytes
    checksum = [string]$Decrypted.Manifest.sha256
}
