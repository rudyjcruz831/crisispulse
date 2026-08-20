param(
    [string]$Address = "127.0.0.1:8080",
    [string]$DataPath = "",
    [string]$ReviewPath = "",
    [string]$AllowedOrigin = "http://localhost:3000"
)

$ErrorActionPreference = "Stop"

$SystemGo = Get-Command go -ErrorAction SilentlyContinue
$PortableGo = "$env:LOCALAPPDATA\CrisisPulse\toolchains\go1.27.0\bin\go.exe"
if ($SystemGo) {
    $GoExecutable = $SystemGo.Source
}
elseif (Test-Path -LiteralPath $PortableGo) {
    $GoExecutable = $PortableGo
}
else {
    throw "Go is not available. Run scripts\setup-go.ps1 once, then retry."
}

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepositoryRoot
try {
    $ApiArguments = @(
        "run", "./cmd/api",
        "--addr", $Address,
        "--allowed-origin", $AllowedOrigin
    )
    if ($DataPath) {
        $ApiArguments += @("--data", $DataPath)
    }
    if ($ReviewPath) {
        $ApiArguments += @("--reviews", $ReviewPath)
    }
    & $GoExecutable @ApiArguments
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $ExitCode
