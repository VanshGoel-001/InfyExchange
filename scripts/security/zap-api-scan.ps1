<#
.SYNOPSIS
    Runs an OWASP ZAP scan against a running InfyExchange target.

.DESCRIPTION
    Mode 'openapi' performs an API scan from the FastAPI OpenAPI document.
    The document is only served when ENVIRONMENT is not 'production'.
    Mode 'baseline' performs a passive baseline scan of a web URL (SPA).
    HTML, Markdown and JSON reports are written to <repo>\zap-reports\.

.PARAMETER Target
    URL reachable from inside the ZAP container. Defaults to the local API
    through Docker Desktop's host.docker.internal alias.

.PARAMETER Mode
    'openapi' (default) or 'baseline'.

.PARAMETER ContextFile
    Optional ZAP context file for authenticated scans.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1 `
        -Mode baseline -Target http://host.docker.internal:5173
#>
param(
    [string]$Target = "http://host.docker.internal:8000/openapi.json",
    [ValidateSet("openapi", "baseline")][string]$Mode = "openapi",
    [string]$ContextFile = ""
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker is not available on PATH"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$reportsDir = Join-Path $repoRoot "zap-reports"
New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

$image = "ghcr.io/zaproxy/zaproxy:stable"
$scan = if ($Mode -eq "openapi") { "zap-api-scan.py" } else { "zap-baseline.py" }

$scanArgs = @(
    $scan, "-t", $Target,
    "-r", "zap-report.html",
    "-w", "zap-report.md",
    "-J", "zap-report.json"
)

if ($Mode -eq "openapi") {
    $scanArgs += @("-f", "openapi")
}

if ($ContextFile) {
    if (-not (Test-Path $ContextFile)) {
        throw "Context file not found: $ContextFile"
    }
    Copy-Item $ContextFile (Join-Path $reportsDir "context.conf") -Force
    $scanArgs += @("-n", "context.conf")
}

Write-Host "Mode    : $Mode"
Write-Host "Target  : $Target"
Write-Host "Reports : $reportsDir"

docker run --rm -v "${reportsDir}:/zap/wrk/:rw" $image @scanArgs
$code = $LASTEXITCODE

switch ($code) {
    0 { Write-Host "ZAP: PASS (no alerts at failure threshold)" }
    1 { Write-Host "ZAP: FAIL (one or more alerts at failure threshold)" }
    default { Write-Host "ZAP: scan error (exit $code)" }
}
Write-Host "Open $reportsDir\zap-report.html for details."

exit $code
