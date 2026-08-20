param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\CrisisPulse\toolchains\go1.27.0"
)

$ErrorActionPreference = "Stop"

$ArchiveUrl = "https://go.dev/dl/go1.27.0.windows-amd64.zip"
$ExpectedSha256 = "f0c0a0d33ba94f4d2c5dbc887334ce678b21813504ddb3aafcb06e60a5a667c4"
$GoExecutable = Join-Path $InstallRoot "bin\go.exe"

if (Test-Path -LiteralPath $GoExecutable) {
    & $GoExecutable version
    exit $LASTEXITCODE
}

if (Test-Path -LiteralPath $InstallRoot) {
    throw "The Go toolchain directory exists but is incomplete: $InstallRoot"
}

$InstallParent = Split-Path -Parent $InstallRoot
$TemporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("crisispulse-go-" + [guid]::NewGuid().ToString("N"))
$ArchivePath = Join-Path $TemporaryRoot "go.zip"
$ExtractRoot = Join-Path $TemporaryRoot "extract"

New-Item -ItemType Directory -Path $TemporaryRoot, $ExtractRoot, $InstallParent -Force | Out-Null

try {
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ArchivePath
    $ActualSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        throw "Go archive checksum mismatch. Expected $ExpectedSha256, received $ActualSha256."
    }

    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExtractRoot
    $ExtractedGo = Join-Path $ExtractRoot "go"
    if (-not (Test-Path -LiteralPath (Join-Path $ExtractedGo "bin\go.exe"))) {
        throw "The verified Go archive did not contain bin\go.exe."
    }
    Move-Item -LiteralPath $ExtractedGo -Destination $InstallRoot
}
finally {
    if (Test-Path -LiteralPath $TemporaryRoot) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
}

& $GoExecutable version
exit $LASTEXITCODE
