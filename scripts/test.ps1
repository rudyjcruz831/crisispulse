$ErrorActionPreference = "Stop"

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "The local environment is missing. Run scripts\setup.ps1 first."
}

& $Python -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

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

& $GoExecutable test ./cmd/...
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path -LiteralPath "dashboard\node_modules")) {
    throw "Dashboard dependencies are missing. Run npm install from the dashboard directory."
}

Push-Location dashboard
try {
    & npm test
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $ExitCode
