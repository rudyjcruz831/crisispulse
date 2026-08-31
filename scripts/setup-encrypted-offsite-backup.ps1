param(
    [string]$ConfigPath = "",
    [string]$OneDriveRoot = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "backup-encryption-common.ps1")

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Get-CrisisPulseDefaultEncryptionConfigPath
}
if (Test-Path -LiteralPath $ConfigPath) {
    throw "Encrypted backup is already configured. Reuse the existing recovery material instead of rotating it."
}

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$EnvironmentPath = Join-Path $RepositoryRoot ".env.production"
if (-not (Test-Path -LiteralPath $EnvironmentPath -PathType Leaf)) {
    throw "The local production environment file is missing."
}
[byte[]]$EnvironmentOriginalBytes = [System.IO.File]::ReadAllBytes($EnvironmentPath)
foreach ($CommandName in @(
    "Protect-CmsMessage",
    "Unprotect-CmsMessage",
    "New-SelfSignedCertificate",
    "Export-PfxCertificate",
    "Export-Certificate"
)) {
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Windows is missing the required backup encryption command '$CommandName'."
    }
}

if ([string]::IsNullOrWhiteSpace($OneDriveRoot)) {
    $AccountKey = "HKCU:\Software\Microsoft\OneDrive\Accounts\Personal"
    if (Test-Path $AccountKey) {
        $OneDriveRoot = [string](Get-ItemProperty $AccountKey).UserFolder
    }
    if ([string]::IsNullOrWhiteSpace($OneDriveRoot)) {
        $OneDriveRoot = [string]$env:OneDriveConsumer
    }
}
if ([string]::IsNullOrWhiteSpace($OneDriveRoot) -or -not (Test-Path -LiteralPath $OneDriveRoot -PathType Container)) {
    throw "The registered OneDrive folder could not be found."
}
$OneDriveRoot = [System.IO.Path]::GetFullPath($OneDriveRoot)

function Test-CrisisPulsePathInside {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $CandidateFull = [System.IO.Path]::GetFullPath($Candidate).TrimEnd("\")
    $RootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd("\")
    $CandidateFull.Equals($RootFull, [System.StringComparison]::OrdinalIgnoreCase) -or
        $CandidateFull.StartsWith($RootFull + "\", [System.StringComparison]::OrdinalIgnoreCase)
}

$RepositoryBackupDirectory = Join-Path $RepositoryRoot "backups"
if (
    (Test-CrisisPulsePathInside -Candidate $RepositoryBackupDirectory -Root $OneDriveRoot) -and
    (Get-ChildItem -LiteralPath $RepositoryBackupDirectory -File -Filter "crisispulse-*.tar.gz" -ErrorAction SilentlyContinue)
) {
    throw "Plaintext repository backups are inside the registered OneDrive folder. Move them outside OneDrive before claiming encrypted-only cloud storage."
}

$ConfigDirectory = Split-Path -Parent $ConfigPath
$LocalBackupDirectory = Join-Path $env:LOCALAPPDATA "CrisisPulse\backups"
$OffsiteDirectory = Join-Path $OneDriveRoot "CrisisPulse Encrypted Backups"
$RecoveryDirectory = Join-Path $OffsiteDirectory "Recovery"
$RecoveryBundlePath = Join-Path $RecoveryDirectory "CrisisPulse-Backup-Recovery-v2.pfx"
$PublicCertificatePath = Join-Path $ConfigDirectory "CrisisPulse-Backup-Recovery-v2.cer"
$RecoveryCodePath = Join-Path $ConfigDirectory "SAVE-THIS-RECOVERY-CODE.txt"

foreach ($Directory in @($ConfigDirectory, $LocalBackupDirectory, $OffsiteDirectory, $RecoveryDirectory)) {
    if (-not (Test-Path -LiteralPath $Directory)) {
        New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    }
}
Set-CrisisPulsePrivateAcl -Path $ConfigDirectory
Set-CrisisPulsePrivateAcl -Path $LocalBackupDirectory

if (Test-Path -LiteralPath $RecoveryBundlePath) {
    throw "A version-2 recovery bundle already exists, so setup will not overwrite it."
}

function Copy-CrisisPulseFileVerified {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        $DestinationHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
        if ($DestinationHash -ne $SourceHash) {
            throw "A local backup migration file already exists with different contents: $(Split-Path -Leaf $Destination)"
        }
        return
    }
    $Temporary = "$Destination.partial.$PID.$([Guid]::NewGuid().ToString('N'))"
    try {
        Copy-Item -LiteralPath $Source -Destination $Temporary
        if ((Get-FileHash -LiteralPath $Temporary -Algorithm SHA256).Hash -ne $SourceHash) {
            throw "A local backup migration checksum failed."
        }
        Move-Item -LiteralPath $Temporary -Destination $Destination
        Set-CrisisPulsePrivateAcl -Path $Destination
    }
    finally {
        if (Test-Path -LiteralPath $Temporary) {
            Remove-Item -LiteralPath $Temporary -Force
        }
    }
}

function Set-CrisisPulseEnvironmentValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    if ($Value.Contains("'")) {
        throw "The backup path contains an unsupported apostrophe."
    }
    $Lines = @(Get-Content -LiteralPath $Path)
    $Replacement = "$Name='$Value'"
    $Found = $false
    for ($Index = 0; $Index -lt $Lines.Count; $Index++) {
        if ($Lines[$Index] -match "^\s*$([Regex]::Escape($Name))=") {
            $Lines[$Index] = $Replacement
            $Found = $true
        }
    }
    if (-not $Found) {
        $Lines += ""
        $Lines += "# Plaintext backups stay local; the registered OneDrive receives authenticated encrypted copies."
        $Lines += $Replacement
    }
    $Text = ($Lines -join [Environment]::NewLine) + [Environment]::NewLine
    Write-CrisisPulseUtf8Atomic -Path $Path -Content $Text
}

$Certificate = $null
$PfxTemporary = "$RecoveryBundlePath.partial.$PID.$([Guid]::NewGuid().ToString('N'))"
$CreatedEncryptedPath = ""
$PublishedRecoveryBundle = $false
$EnvironmentMutated = $false
try {
    $Certificate = New-SelfSignedCertificate `
        -Subject "CN=CrisisPulse Backup Recovery v2" `
        -FriendlyName "CrisisPulse authenticated encrypted backup recovery" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -Type DocumentEncryptionCert `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -KeyExportPolicy Exportable `
        -NotAfter ([DateTime]::UtcNow.AddYears(10))

    $RandomBytes = New-Object byte[] 32
    $Random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $Random.GetBytes($RandomBytes)
    }
    finally {
        $Random.Dispose()
    }
    $RecoveryPasswordText = [Convert]::ToBase64String($RandomBytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    $RecoveryPassword = ConvertTo-SecureString -String $RecoveryPasswordText -AsPlainText -Force

    [byte[]]$AuthenticationKey = New-Object byte[] 32
    $Random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $Random.GetBytes($AuthenticationKey)
    }
    finally {
        $Random.Dispose()
    }
    $AuthenticationKeyText = [Convert]::ToBase64String($AuthenticationKey).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    $ProtectedAuthenticationKey = Protect-CrisisPulseAuthenticationKeyForCurrentUser `
        -AuthenticationKey $AuthenticationKey

    # Exercise the actual Windows PowerShell crypto path before changing backup
    # mounts or publishing configuration.
    $PreflightPlaintext = '{"crisispulse_backup_preflight":2}'
    $PreflightCms = Protect-CmsMessage -To $Certificate -Content $PreflightPlaintext
    if ((Unprotect-CmsMessage -Content $PreflightCms) -ne $PreflightPlaintext) {
        throw "The installed certificate failed its encryption preflight."
    }
    Export-PfxCertificate `
        -Cert $Certificate `
        -FilePath $PfxTemporary `
        -Password $RecoveryPassword `
        -ChainOption EndEntityCertOnly `
        -NoProperties | Out-Null
    if ((ConvertFrom-CrisisPulseCmsWithPfx `
        -CmsText $PreflightCms `
        -PfxPath $PfxTemporary `
        -PfxPassword $RecoveryPassword) -ne $PreflightPlaintext) {
        throw "The exported recovery bundle failed its independent encryption preflight."
    }

    if (Test-Path -LiteralPath $RepositoryBackupDirectory -PathType Container) {
        $MigrationFiles = Get-ChildItem -LiteralPath $RepositoryBackupDirectory -File | Where-Object {
            $_.Name -eq "backup-status.json" -or
            $_.Name -match "^crisispulse-\d{8}T\d{6}Z\.tar\.gz(\.sha256)?$"
        }
        foreach ($File in $MigrationFiles) {
            $MigrationDestination = Join-Path $LocalBackupDirectory $File.Name
            # A live local status may be newer than the repository fallback
            # after the bind mount has already been switched. Never replace it
            # with an older status record during a safe setup retry.
            if ($File.Name -eq "backup-status.json" -and (Test-Path -LiteralPath $MigrationDestination)) {
                continue
            }
            Copy-CrisisPulseFileVerified `
                -Source $File.FullName `
                -Destination $MigrationDestination
        }
    }
    Get-ChildItem -LiteralPath $LocalBackupDirectory -File | ForEach-Object {
        Set-CrisisPulsePrivateAcl -Path $_.FullName
    }

    $VerifiedBackup = Get-CrisisPulseVerifiedLocalBackup -BackupDirectory $LocalBackupDirectory
    $Encrypted = Protect-CrisisPulseVerifiedBackup `
        -VerifiedBackup $VerifiedBackup `
        -DestinationDirectory $OffsiteDirectory `
        -CertificateThumbprint $Certificate.Thumbprint `
        -AuthenticationKey $AuthenticationKey `
        -MaxArchiveBytes 67108864
    if ($Encrypted.Publication -eq "new") {
        $CreatedEncryptedPath = $Encrypted.EncryptedPath
    }

    $RecoveryTest = Test-CrisisPulseEncryptedBackup `
        -EncryptedBackupPath $Encrypted.EncryptedPath `
        -AuthenticationKey $AuthenticationKey `
        -RecoveryBundlePath $PfxTemporary `
        -RecoveryPassword $RecoveryPassword
    if (
        $RecoveryTest.ArchiveName -ne $VerifiedBackup.ArchiveName -or
        $RecoveryTest.ArchiveBytes -ne $VerifiedBackup.ArchiveBytes -or
        $RecoveryTest.Checksum -ne $VerifiedBackup.Checksum
    ) {
        throw "The exported recovery bundle test did not match the local backup."
    }

    Move-Item -LiteralPath $PfxTemporary -Destination $RecoveryBundlePath
    $PublishedRecoveryBundle = $true
    Export-Certificate -Cert $Certificate -FilePath $PublicCertificatePath -Type CERT | Out-Null
    Set-CrisisPulsePrivateAcl -Path $PublicCertificatePath

    $RecoveryCode = @"
CRISISPULSE BACKUP RECOVERY CODE

Recovery password:
$RecoveryPasswordText

Recovery authentication key:
$AuthenticationKeyText

Recovery bundle in OneDrive:
$RecoveryBundlePath

Certificate thumbprint:
$($Certificate.Thumbprint)

IMPORTANT: Save both recovery values outside this computer now. Put them in a
password manager or write them on paper. Do not keep the only copy on this PC or
in the same OneDrive account as the recovery bundle.

The recovery bundle, password, and authentication key restored and verified:
$($RecoveryTest.ArchiveName)
$($RecoveryTest.Checksum)
"@
    Write-CrisisPulseUtf8Atomic -Path $RecoveryCodePath -Content $RecoveryCode
    Set-CrisisPulsePrivateAcl -Path $RecoveryCodePath

    $OffsiteReadme = @"
CrisisPulse authenticated encrypted backups

The .cpbackup.p7m files in this folder are encrypted and authenticated before
OneDrive receives them. The Recovery folder contains the password-protected
private recovery bundle.

To recover after losing the PC, clone the CrisisPulse repository and run:
scripts\restore-encrypted-offsite-backup.ps1

You will need both values from the recovery code saved separately in a password
manager or on paper. Neither recovery value is stored in OneDrive.
"@
    Write-CrisisPulseUtf8Atomic `
        -Path (Join-Path $OffsiteDirectory "README-RECOVERY.txt") `
        -Content $OffsiteReadme

    $LocalBackupComposePath = $LocalBackupDirectory.Replace("\", "/")
    Set-CrisisPulseEnvironmentValue `
        -Path $EnvironmentPath `
        -Name "CRISISPULSE_BACKUP_DIR" `
        -Value $LocalBackupComposePath
    $EnvironmentMutated = $true

    $Config = [ordered]@{
        schema_version = 2
        created_at_utc = [DateTime]::UtcNow.ToString("o")
        local_backup_directory = [System.IO.Path]::GetFullPath($LocalBackupDirectory)
        offsite_directory = [System.IO.Path]::GetFullPath($OffsiteDirectory)
        certificate_thumbprint = $Certificate.Thumbprint
        certificate_expires_at_utc = $Certificate.NotAfter.ToUniversalTime().ToString("o")
        recovery_bundle_path = [System.IO.Path]::GetFullPath($RecoveryBundlePath)
        max_archive_bytes = 67108864
        authentication_scheme = "HMAC-SHA256-DPAPI-v1"
        protected_authentication_key = $ProtectedAuthenticationKey
    }
    Write-CrisisPulseUtf8Atomic `
        -Path $ConfigPath `
        -Content ($Config | ConvertTo-Json)
    Set-CrisisPulsePrivateAcl -Path $ConfigPath

    [pscustomobject]@{
        status = "configured"
        local_backup_directory = $LocalBackupDirectory
        offsite_directory = $OffsiteDirectory
        encrypted_backup = $Encrypted.EncryptedPath
        recovery_bundle = $RecoveryBundlePath
        recovery_code_path = $RecoveryCodePath
        pfx_recovery_test = "verified"
        authentication_test = "verified"
        cloud_visibility_confirmed = $false
    }
}
catch {
    $OriginalError = $_
    $EnvironmentRollbackError = ""
    if ($EnvironmentMutated) {
        $EnvironmentRollback = "$EnvironmentPath.rollback.$PID.$([Guid]::NewGuid().ToString('N'))"
        try {
            [System.IO.File]::WriteAllBytes($EnvironmentRollback, $EnvironmentOriginalBytes)
            Move-Item -LiteralPath $EnvironmentRollback -Destination $EnvironmentPath -Force
        }
        catch {
            $EnvironmentRollbackError = $_.Exception.Message
        }
        finally {
            if (Test-Path -LiteralPath $EnvironmentRollback -PathType Leaf) {
                Remove-Item -LiteralPath $EnvironmentRollback -Force
            }
        }
    }
    $RollbackPaths = @($ConfigPath, $RecoveryCodePath, $PublicCertificatePath)
    if ($PublishedRecoveryBundle) {
        $RollbackPaths += $RecoveryBundlePath
    }
    if (-not [string]::IsNullOrWhiteSpace($CreatedEncryptedPath)) {
        $RollbackPaths += $CreatedEncryptedPath
    }
    foreach ($RollbackPath in $RollbackPaths) {
        if (Test-Path -LiteralPath $RollbackPath -PathType Leaf) {
            Remove-Item -LiteralPath $RollbackPath -Force
        }
    }
    if ($Certificate) {
        Remove-Item -LiteralPath ("Cert:\CurrentUser\My\" + $Certificate.Thumbprint) -Force -ErrorAction SilentlyContinue
    }
    if (-not [string]::IsNullOrWhiteSpace($EnvironmentRollbackError)) {
        throw "Encrypted backup setup failed and the production environment file could not be restored: $EnvironmentRollbackError"
    }
    throw $OriginalError
}
finally {
    if (Test-Path -LiteralPath $PfxTemporary -PathType Leaf) {
        Remove-Item -LiteralPath $PfxTemporary -Force
    }
}
