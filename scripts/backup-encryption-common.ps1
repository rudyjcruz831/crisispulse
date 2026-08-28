Set-StrictMode -Version Latest

function Get-CrisisPulseDefaultEncryptionConfigPath {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "LOCALAPPDATA is unavailable."
    }
    Join-Path $env:LOCALAPPDATA "CrisisPulse\backup-encryption\config.json"
}

function Get-CrisisPulseSha256FromBytes {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    $Hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $HashBytes = $Hasher.ComputeHash($Bytes)
        ([System.BitConverter]::ToString($HashBytes) -replace "-", "").ToLowerInvariant()
    }
    finally {
        $Hasher.Dispose()
    }
}

function Write-CrisisPulseUtf8Atomic {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $Parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $Parent)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    $Temporary = "$Path.partial.$PID.$([Guid]::NewGuid().ToString('N'))"
    $Encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    try {
        [System.IO.File]::WriteAllText($Temporary, $Content, $Encoding)
        Move-Item -LiteralPath $Temporary -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $Temporary) {
            Remove-Item -LiteralPath $Temporary -Force
        }
    }
}

function Set-CrisisPulsePrivateAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    $Item = Get-Item -LiteralPath $Path
    $CurrentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($Item.PSIsContainer) {
        $CurrentRule = "*$($CurrentSid.Value):(OI)(CI)F"
        $SystemRule = "*S-1-5-18:(OI)(CI)F"
    }
    else {
        $CurrentRule = "*$($CurrentSid.Value):F"
        $SystemRule = "*S-1-5-18:F"
    }
    & icacls.exe $Item.FullName /inheritance:r /grant:r $CurrentRule $SystemRule /Q | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Windows could not restrict access to the local CrisisPulse backup material."
    }
}

function Get-CrisisPulseEncryptionConfig {
    param([Parameter(Mandatory = $true)][string]$ConfigPath)

    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw "Encrypted backup configuration is missing: $ConfigPath"
    }
    try {
        $Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    }
    catch {
        throw "Encrypted backup configuration is not valid JSON."
    }
    foreach ($Required in @(
        "schema_version",
        "local_backup_directory",
        "offsite_directory",
        "certificate_thumbprint",
        "recovery_bundle_path",
        "max_archive_bytes",
        "authentication_scheme",
        "protected_authentication_key"
    )) {
        if ($Config.PSObject.Properties.Name -notcontains $Required) {
            throw "Encrypted backup configuration is missing '$Required'."
        }
    }
    if ([int]$Config.schema_version -ne 2) {
        throw "Unsupported encrypted backup configuration version."
    }
    if (
        [int64]$Config.max_archive_bytes -lt 1 -or
        [int64]$Config.max_archive_bytes -gt 67108864
    ) {
        throw "Encrypted backup maximum archive size is invalid."
    }
    if ([string]$Config.authentication_scheme -ne "HMAC-SHA256-DPAPI-v1") {
        throw "Unsupported encrypted backup authentication scheme."
    }
    $Config
}

function Get-CrisisPulseEncryptionCertificate {
    param([Parameter(Mandatory = $true)][string]$Thumbprint)

    $Normalized = ($Thumbprint -replace "\s", "").ToUpperInvariant()
    if ($Normalized -notmatch "^[A-F0-9]{40}$") {
        throw "Encrypted backup certificate thumbprint is invalid."
    }
    $Certificate = Get-ChildItem -Path Cert:\CurrentUser\My | Where-Object {
        $_.Thumbprint -eq $Normalized
    } | Select-Object -First 1
    if (-not $Certificate) {
        throw "The CrisisPulse backup encryption certificate is not installed for this Windows user."
    }
    $Certificate
}

function Protect-CrisisPulseAuthenticationKeyForCurrentUser {
    param([Parameter(Mandatory = $true)][byte[]]$AuthenticationKey)

    if ($AuthenticationKey.Length -ne 32) {
        throw "The backup authentication key must be 32 bytes."
    }
    Add-Type -AssemblyName System.Security
    $Entropy = [System.Text.Encoding]::UTF8.GetBytes("CrisisPulse authenticated backup v2")
    $Protected = [System.Security.Cryptography.ProtectedData]::Protect(
        $AuthenticationKey,
        $Entropy,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    [Convert]::ToBase64String($Protected)
}

function Get-CrisisPulseAuthenticationKeyForCurrentUser {
    param([Parameter(Mandatory = $true)]$Config)

    try {
        $Protected = [Convert]::FromBase64String([string]$Config.protected_authentication_key)
        Add-Type -AssemblyName System.Security
        $Entropy = [System.Text.Encoding]::UTF8.GetBytes("CrisisPulse authenticated backup v2")
        [byte[]]$Key = [System.Security.Cryptography.ProtectedData]::Unprotect(
            $Protected,
            $Entropy,
            [System.Security.Cryptography.DataProtectionScope]::CurrentUser
        )
    }
    catch {
        throw "The local backup authentication key cannot be unlocked by this Windows user."
    }
    if ($Key.Length -ne 32) {
        throw "The local backup authentication key is invalid."
    }
    return ,$Key
}

function ConvertFrom-CrisisPulseRecoveryAuthenticationKey {
    param([Parameter(Mandatory = $true)][securestring]$AuthenticationKey)

    $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($AuthenticationKey)
    try {
        $Text = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
        $Padded = $Text.Replace("-", "+").Replace("_", "/")
        while ($Padded.Length % 4 -ne 0) {
            $Padded += "="
        }
        [byte[]]$Bytes = [Convert]::FromBase64String($Padded)
    }
    catch {
        throw "The recovery authentication key is invalid."
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
    }
    if ($Bytes.Length -ne 32) {
        throw "The recovery authentication key is invalid."
    }
    return ,$Bytes
}

function Get-CrisisPulseAuthenticationTag {
    param(
        [Parameter(Mandatory = $true)][byte[]]$AuthenticationKey,
        [Parameter(Mandatory = $true)][string]$ArchiveName,
        [Parameter(Mandatory = $true)][int64]$ArchiveBytes,
        [Parameter(Mandatory = $true)][string]$Checksum,
        [Parameter(Mandatory = $true)][string]$CreatedAtUtc,
        [Parameter(Mandatory = $true)][byte[]]$PayloadBytes
    )

    if ($AuthenticationKey.Length -ne 32) {
        throw "The backup authentication key must be 32 bytes."
    }
    $Header = "CrisisPulse authenticated backup v2`n$ArchiveName`n$ArchiveBytes`n$Checksum`n$CreatedAtUtc`n"
    [byte[]]$HeaderBytes = [System.Text.Encoding]::UTF8.GetBytes($Header)
    $Hmac = New-Object System.Security.Cryptography.HMACSHA256 -ArgumentList (, $AuthenticationKey)
    try {
        [void]$Hmac.TransformBlock($HeaderBytes, 0, $HeaderBytes.Length, $HeaderBytes, 0)
        [void]$Hmac.TransformFinalBlock($PayloadBytes, 0, $PayloadBytes.Length)
        ([System.BitConverter]::ToString($Hmac.Hash) -replace "-", "").ToLowerInvariant()
    }
    finally {
        $Hmac.Dispose()
    }
}

function Test-CrisisPulseFixedTimeHexEqual {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )

    if ($Left.Length -ne 64 -or $Right.Length -ne 64) {
        return $false
    }
    $Difference = 0
    for ($Index = 0; $Index -lt 64; $Index += 2) {
        $LeftByte = [Convert]::ToByte($Left.Substring($Index, 2), 16)
        $RightByte = [Convert]::ToByte($Right.Substring($Index, 2), 16)
        $Difference = $Difference -bor ($LeftByte -bxor $RightByte)
    }
    $Difference -eq 0
}

function Get-CrisisPulseVerifiedLocalBackup {
    param([Parameter(Mandatory = $true)][string]$BackupDirectory)

    $Root = [System.IO.Path]::GetFullPath($BackupDirectory)
    $StatusPath = Join-Path $Root "backup-status.json"
    if (-not (Test-Path -LiteralPath $StatusPath -PathType Leaf)) {
        throw "The verified backup status file is missing."
    }
    try {
        $Status = Get-Content -LiteralPath $StatusPath -Raw | ConvertFrom-Json
    }
    catch {
        throw "The verified backup status file is invalid."
    }
    if (
        [int]$Status.schema_version -ne 2 -or
        $Status.status -ne "verified" -or
        $Status.application_data_verified -ne $true
    ) {
        throw "The latest local backup is not marked as application-data verified."
    }
    $ArchiveName = [string]$Status.archive_name
    if ($ArchiveName -notmatch "^crisispulse-\d{8}T\d{6}Z\.tar\.gz$") {
        throw "The verified backup status contains an unsafe archive name."
    }
    $ArchivePath = Join-Path $Root $ArchiveName
    $SidecarPath = "$ArchivePath.sha256"
    if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
        throw "The verified local backup archive is missing."
    }
    if (-not (Test-Path -LiteralPath $SidecarPath -PathType Leaf)) {
        throw "The verified local backup checksum sidecar is missing."
    }
    $Sidecar = (Get-Content -LiteralPath $SidecarPath -Raw).Trim()
    if ($Sidecar -notmatch "^([A-Fa-f0-9]{64})  (crisispulse-\d{8}T\d{6}Z\.tar\.gz)$") {
        throw "The local backup checksum sidecar is invalid."
    }
    $SidecarChecksum = $Matches[1].ToLowerInvariant()
    if ($Matches[2] -ne $ArchiveName) {
        throw "The local backup checksum names a different archive."
    }
    $StatusChecksum = ([string]$Status.checksum).ToLowerInvariant()
    if ($StatusChecksum -notmatch "^[a-f0-9]{64}$" -or $StatusChecksum -ne $SidecarChecksum) {
        throw "The local backup status and checksum sidecar disagree."
    }
    $Archive = Get-Item -LiteralPath $ArchivePath
    if ($Archive.Length -ne [int64]$Status.archive_bytes) {
        throw "The local backup size does not match its verified status."
    }
    $CalculatedChecksum = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($CalculatedChecksum -ne $StatusChecksum) {
        throw "The local backup checksum verification failed."
    }
    [pscustomobject]@{
        ArchiveName = $ArchiveName
        ArchivePath = $Archive.FullName
        ArchiveBytes = [int64]$Archive.Length
        Checksum = $CalculatedChecksum
        VerifiedAtUtc = [string]$Status.verified_at
    }
}

function ConvertFrom-CrisisPulseCmsWithPfx {
    param(
        [Parameter(Mandatory = $true)][string]$CmsText,
        [Parameter(Mandatory = $true)][string]$PfxPath,
        [Parameter(Mandatory = $true)][securestring]$PfxPassword
    )

    if (-not (Test-Path -LiteralPath $PfxPath -PathType Leaf)) {
        throw "The recovery bundle is missing."
    }
    Add-Type -AssemblyName System.Security
    $Base64 = (($CmsText -split "`r?`n") | Where-Object {
        $_ -and $_ -notmatch "^-----"
    }) -join ""
    try {
        $CmsBytes = [Convert]::FromBase64String($Base64)
    }
    catch {
        throw "The encrypted backup is not valid CMS data."
    }
    $Flags = [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet
    $Certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 `
        -ArgumentList @($PfxPath, $PfxPassword, $Flags)
    try {
        if (-not $Certificate.HasPrivateKey) {
            throw "The recovery bundle does not contain its private key."
        }
        $Envelope = New-Object System.Security.Cryptography.Pkcs.EnvelopedCms
        $Envelope.Decode($CmsBytes)
        $Certificates = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2Collection
        [void]$Certificates.Add($Certificate)
        $Envelope.Decrypt($Certificates)
        [System.Text.Encoding]::UTF8.GetString($Envelope.ContentInfo.Content)
    }
    finally {
        $Certificate.Dispose()
    }
}

function Read-CrisisPulseEncryptedBackup {
    [CmdletBinding(DefaultParameterSetName = "InstalledCertificate")]
    param(
        [Parameter(Mandatory = $true)][string]$EncryptedBackupPath,
        [Parameter(Mandatory = $true)][byte[]]$AuthenticationKey,
        [Parameter(Mandatory = $true, ParameterSetName = "InstalledCertificate")][string]$CertificateThumbprint,
        [Parameter(Mandatory = $true, ParameterSetName = "RecoveryBundle")][string]$RecoveryBundlePath,
        [Parameter(Mandatory = $true, ParameterSetName = "RecoveryBundle")][securestring]$RecoveryPassword
    )

    if (-not (Test-Path -LiteralPath $EncryptedBackupPath -PathType Leaf)) {
        throw "The encrypted backup file is missing."
    }
    $EncryptedFile = Get-Item -LiteralPath $EncryptedBackupPath
    # A 64 MiB archive expands to roughly 117 MiB after base64 and CMS armor.
    # Reject untrusted offsite input before ReadAllText can allocate without a
    # bound; creation uses a much smaller exact archive limit below.
    if ($EncryptedFile.Length -lt 1 -or $EncryptedFile.Length -gt 134217728) {
        throw "The encrypted backup exceeds the safe restore input limit."
    }
    $CmsText = [System.IO.File]::ReadAllText($EncryptedFile.FullName)
    if ($PSCmdlet.ParameterSetName -eq "RecoveryBundle") {
        $Json = ConvertFrom-CrisisPulseCmsWithPfx `
            -CmsText $CmsText `
            -PfxPath $RecoveryBundlePath `
            -PfxPassword $RecoveryPassword
    }
    else {
        [void](Get-CrisisPulseEncryptionCertificate -Thumbprint $CertificateThumbprint)
        try {
            $Json = Unprotect-CmsMessage -Content $CmsText
        }
        catch {
            throw "The encrypted backup could not be decrypted with the installed recovery certificate."
        }
    }
    try {
        $Payload = $Json | ConvertFrom-Json
    }
    catch {
        throw "The decrypted backup payload is invalid."
    }
    foreach ($Required in @(
        "schema_version",
        "archive_name",
        "archive_bytes",
        "sha256",
        "created_at_utc",
        "authentication",
        "authentication_tag",
        "payload_base64"
    )) {
        if ($Payload.PSObject.Properties.Name -notcontains $Required) {
            throw "The decrypted backup payload is missing '$Required'."
        }
    }
    if ([int]$Payload.schema_version -ne 2) {
        throw "Unsupported encrypted backup payload version."
    }
    if ([string]$Payload.authentication -ne "HMAC-SHA256-v1") {
        throw "Unsupported encrypted backup authentication format."
    }
    if ([string]$Payload.archive_name -notmatch "^crisispulse-\d{8}T\d{6}Z\.tar\.gz$") {
        throw "The decrypted backup contains an unsafe archive name."
    }
    if ([string]$Payload.sha256 -notmatch "^[a-f0-9]{64}$") {
        throw "The decrypted backup checksum is invalid."
    }
    try {
        $DeclaredArchiveBytes = [int64]$Payload.archive_bytes
    }
    catch {
        throw "The decrypted backup size is invalid."
    }
    if ($DeclaredArchiveBytes -lt 1 -or $DeclaredArchiveBytes -gt 67108864) {
        throw "The decrypted backup exceeds the safe restore archive limit."
    }
    $ExpectedBase64Length = [int64]([Math]::Ceiling($DeclaredArchiveBytes / 3.0) * 4)
    if (([string]$Payload.payload_base64).Length -ne $ExpectedBase64Length) {
        throw "The decrypted backup base64 size is inconsistent with its manifest."
    }
    try {
        [byte[]]$Bytes = [Convert]::FromBase64String([string]$Payload.payload_base64)
    }
    catch {
        throw "The decrypted backup data is not valid base64."
    }
    if ($Bytes.LongLength -ne $DeclaredArchiveBytes) {
        throw "The decrypted backup size verification failed."
    }
    $Checksum = Get-CrisisPulseSha256FromBytes -Bytes $Bytes
    if ($Checksum -ne [string]$Payload.sha256) {
        throw "The decrypted backup checksum verification failed."
    }
    if ([string]$Payload.authentication_tag -notmatch "^[a-f0-9]{64}$") {
        throw "The decrypted backup authentication tag is invalid."
    }
    $ExpectedAuthenticationTag = Get-CrisisPulseAuthenticationTag `
        -AuthenticationKey $AuthenticationKey `
        -ArchiveName ([string]$Payload.archive_name) `
        -ArchiveBytes ([int64]$Payload.archive_bytes) `
        -Checksum ([string]$Payload.sha256) `
        -CreatedAtUtc ([string]$Payload.created_at_utc) `
        -PayloadBytes $Bytes
    if (-not (Test-CrisisPulseFixedTimeHexEqual `
        -Left $ExpectedAuthenticationTag `
        -Right ([string]$Payload.authentication_tag))) {
        throw "The encrypted backup authentication verification failed."
    }
    [pscustomobject]@{
        Manifest = $Payload
        Bytes = $Bytes
    }
}

function Test-CrisisPulseEncryptedBackup {
    [CmdletBinding(DefaultParameterSetName = "InstalledCertificate")]
    param(
        [Parameter(Mandatory = $true)][string]$EncryptedBackupPath,
        [Parameter(Mandatory = $true)][byte[]]$AuthenticationKey,
        [Parameter(Mandatory = $true, ParameterSetName = "InstalledCertificate")][string]$CertificateThumbprint,
        [Parameter(Mandatory = $true, ParameterSetName = "RecoveryBundle")][string]$RecoveryBundlePath,
        [Parameter(Mandatory = $true, ParameterSetName = "RecoveryBundle")][securestring]$RecoveryPassword
    )

    if ($PSCmdlet.ParameterSetName -eq "RecoveryBundle") {
        $Result = Read-CrisisPulseEncryptedBackup `
            -EncryptedBackupPath $EncryptedBackupPath `
            -AuthenticationKey $AuthenticationKey `
            -RecoveryBundlePath $RecoveryBundlePath `
            -RecoveryPassword $RecoveryPassword
    }
    else {
        $Result = Read-CrisisPulseEncryptedBackup `
            -EncryptedBackupPath $EncryptedBackupPath `
            -AuthenticationKey $AuthenticationKey `
            -CertificateThumbprint $CertificateThumbprint
    }
    [pscustomobject]@{
        Status = "verified"
        ArchiveName = [string]$Result.Manifest.archive_name
        ArchiveBytes = [int64]$Result.Manifest.archive_bytes
        Checksum = [string]$Result.Manifest.sha256
        CreatedAtUtc = [string]$Result.Manifest.created_at_utc
        EncryptedPath = (Get-Item -LiteralPath $EncryptedBackupPath).FullName
        EncryptedBytes = (Get-Item -LiteralPath $EncryptedBackupPath).Length
    }
}

function Protect-CrisisPulseVerifiedBackup {
    param(
        [Parameter(Mandatory = $true)]$VerifiedBackup,
        [Parameter(Mandatory = $true)][string]$DestinationDirectory,
        [Parameter(Mandatory = $true)][string]$CertificateThumbprint,
        [Parameter(Mandatory = $true)][byte[]]$AuthenticationKey,
        [Parameter(Mandatory = $true)][int64]$MaxArchiveBytes
    )

    if ($MaxArchiveBytes -gt 67108864 -or $VerifiedBackup.ArchiveBytes -gt $MaxArchiveBytes) {
        throw "The local archive exceeds the safe CMS encryption limit. Use a streaming backup format before continuing."
    }
    if (-not (Test-Path -LiteralPath $DestinationDirectory)) {
        New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
    }
    $Certificate = Get-CrisisPulseEncryptionCertificate -Thumbprint $CertificateThumbprint
    $Destination = Join-Path $DestinationDirectory ($VerifiedBackup.ArchiveName + ".cpbackup.p7m")
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        $Existing = Test-CrisisPulseEncryptedBackup `
            -EncryptedBackupPath $Destination `
            -AuthenticationKey $AuthenticationKey `
            -CertificateThumbprint $CertificateThumbprint
        if (
            $Existing.ArchiveName -ne $VerifiedBackup.ArchiveName -or
            $Existing.ArchiveBytes -ne $VerifiedBackup.ArchiveBytes -or
            $Existing.Checksum -ne $VerifiedBackup.Checksum
        ) {
            throw "An encrypted file already exists for this timestamp but does not match the verified local backup."
        }
        $Existing | Add-Member -NotePropertyName Publication -NotePropertyValue "already_verified"
        return $Existing
    }

    [byte[]]$ArchiveBytes = [System.IO.File]::ReadAllBytes($VerifiedBackup.ArchivePath)
    $CreatedAtUtc = [DateTime]::UtcNow.ToString("o")
    $AuthenticationTag = Get-CrisisPulseAuthenticationTag `
        -AuthenticationKey $AuthenticationKey `
        -ArchiveName $VerifiedBackup.ArchiveName `
        -ArchiveBytes ([int64]$VerifiedBackup.ArchiveBytes) `
        -Checksum $VerifiedBackup.Checksum `
        -CreatedAtUtc $CreatedAtUtc `
        -PayloadBytes $ArchiveBytes
    $Payload = [ordered]@{
        schema_version = 2
        archive_name = $VerifiedBackup.ArchiveName
        archive_bytes = [int64]$VerifiedBackup.ArchiveBytes
        sha256 = $VerifiedBackup.Checksum
        created_at_utc = $CreatedAtUtc
        authentication = "HMAC-SHA256-v1"
        authentication_tag = $AuthenticationTag
        payload_base64 = [Convert]::ToBase64String($ArchiveBytes)
    }
    $Json = $Payload | ConvertTo-Json -Compress
    try {
        $CmsText = Protect-CmsMessage -To $Certificate -Content $Json
    }
    catch {
        throw "Windows could not encrypt the verified backup."
    }
    $Temporary = "$Destination.partial.$PID.$([Guid]::NewGuid().ToString('N'))"
    $Encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    try {
        [System.IO.File]::WriteAllText($Temporary, $CmsText, $Encoding)
        $VerifiedEncrypted = Test-CrisisPulseEncryptedBackup `
            -EncryptedBackupPath $Temporary `
            -AuthenticationKey $AuthenticationKey `
            -CertificateThumbprint $CertificateThumbprint
        if (
            $VerifiedEncrypted.ArchiveName -ne $VerifiedBackup.ArchiveName -or
            $VerifiedEncrypted.ArchiveBytes -ne $VerifiedBackup.ArchiveBytes -or
            $VerifiedEncrypted.Checksum -ne $VerifiedBackup.Checksum
        ) {
            throw "The encrypted backup round-trip verification failed."
        }
        Move-Item -LiteralPath $Temporary -Destination $Destination
    }
    finally {
        if (Test-Path -LiteralPath $Temporary) {
            Remove-Item -LiteralPath $Temporary -Force
        }
    }
    $Published = Test-CrisisPulseEncryptedBackup `
        -EncryptedBackupPath $Destination `
        -AuthenticationKey $AuthenticationKey `
        -CertificateThumbprint $CertificateThumbprint
    $Published | Add-Member -NotePropertyName Publication -NotePropertyValue "new"
    $Published
}
