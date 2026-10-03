[CmdletBinding()]
param(
    [switch]$PreflightOnly,
    [switch]$SkipWebBuild
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$webRoot = Join-Path $repoRoot "apps\web"
$webDist = Join-Path $webRoot "dist"
$webIndex = Join-Path $webDist "index.html"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "SeaWatch Python environment not found at .venv\Scripts\python.exe."
}

$identityKey = [Environment]::GetEnvironmentVariable(
    "SEAWATCH_IDENTITY_KEY",
    [EnvironmentVariableTarget]::Process
)
if ([string]::IsNullOrWhiteSpace($identityKey)) {
    throw "SEAWATCH_IDENTITY_KEY is required. Supply the same stable key used by live and historical identity."
}

$datalasticKey = [Environment]::GetEnvironmentVariable(
    "DATALASTIC_API_KEY",
    [EnvironmentVariableTarget]::Process
)
$datalasticConfigured = -not [string]::IsNullOrWhiteSpace($datalasticKey)
if ($datalasticConfigured) {
    Write-Host "Datalastic API key: configured"
}
else {
    Write-Host "Datalastic API key: not configured"
}

$areaScanSigningKey = [Environment]::GetEnvironmentVariable(
    "SEAWATCH_AREA_SCAN_SIGNING_KEY",
    [EnvironmentVariableTarget]::Process
)
$areaScanOperatorKey = [Environment]::GetEnvironmentVariable(
    "SEAWATCH_AREA_SCAN_OPERATOR_KEY",
    [EnvironmentVariableTarget]::Process
)
$areaScanConfigured = (
    -not [string]::IsNullOrWhiteSpace($areaScanSigningKey) -and
    -not [string]::IsNullOrWhiteSpace($areaScanOperatorKey) -and
    $areaScanSigningKey.Length -ge 32 -and
    $areaScanOperatorKey.Length -ge 32
)
if ($areaScanConfigured) {
    Write-Host "Area Scan operator session: configured"
}
else {
    Write-Host "Area Scan operator session: not configured (endpoint fails closed)"
}

$insecureCookieSetting = [Environment]::GetEnvironmentVariable(
    "SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE",
    [EnvironmentVariableTarget]::Process
)
$allowInsecureCookie = (
    -not [string]::IsNullOrWhiteSpace($insecureCookieSetting) -and
    @("1", "true", "yes", "on") -contains $insecureCookieSetting.Trim().ToLowerInvariant()
)
if ($allowInsecureCookie) {
    Write-Host "Area Scan cookie: local HTTP opt-in enabled"
}
else {
    Write-Host "Area Scan cookie: HTTPS required (secure default)"
}

if (Test-Path Env:SEAWATCH_LIVE_INGEST) {
    Write-Host "SEAWATCH_LIVE_INGEST=$($env:SEAWATCH_LIVE_INGEST) (explicit configuration preserved)"
}
elseif ($datalasticConfigured) {
    $env:SEAWATCH_LIVE_INGEST = "false"
    Write-Host "SEAWATCH_LIVE_INGEST=false (Datalastic Area Scan default)"
}
else {
    $env:SEAWATCH_LIVE_INGEST = "true"
    Write-Host "SEAWATCH_LIVE_INGEST=true (demo default)"
}

$env:SEAWATCH_SERVE_WEB = "true"
$env:SEAWATCH_WEB_DIST = $webDist

if (-not $SkipWebBuild) {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $npm) {
        throw "npm.cmd is required to build the SeaWatch web application."
    }
    $backendEnvironment = @{}
    $backendEnvironmentNames = @(
        Get-ChildItem Env: |
            Where-Object {
                $_.Name -like "SEAWATCH_*" -or
                $_.Name -like "DATALASTIC_*" -or
                $_.Name -eq "GFW_API_TOKEN"
            } |
            ForEach-Object { $_.Name }
    )
    foreach ($name in $backendEnvironmentNames) {
        $backendEnvironment[$name] = [Environment]::GetEnvironmentVariable(
            $name,
            [EnvironmentVariableTarget]::Process
        )
        [Environment]::SetEnvironmentVariable(
            $name,
            $null,
            [EnvironmentVariableTarget]::Process
        )
    }
    Push-Location $webRoot
    try {
        & $npm.Source run build
        if ($LASTEXITCODE -ne 0) {
            throw "SeaWatch web build failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
        foreach ($name in $backendEnvironmentNames) {
            [Environment]::SetEnvironmentVariable(
                $name,
                $backendEnvironment[$name],
                [EnvironmentVariableTarget]::Process
            )
        }
    }
}

if (-not (Test-Path -LiteralPath $webIndex -PathType Leaf)) {
    throw "SeaWatch web build is unavailable. Run without -SkipWebBuild first."
}

Write-Host "SEAWATCH_IDENTITY_KEY=provided (value hidden)"
Write-Host "SeaWatch demo preflight passed."
Write-Warning "Live-provider connectivity is non-blocking. If it fails, the API remains available and /live/health reports the degraded state."

if ($PreflightOnly) {
    return
}

Set-Location $repoRoot
Write-Host "Starting SeaWatch at http://127.0.0.1:8000/"
& $python -m uvicorn apps.api.seawatch.main:app --host 127.0.0.1 --port 8000
if ($LASTEXITCODE -ne 0) {
    throw "SeaWatch API exited with code $LASTEXITCODE."
}
