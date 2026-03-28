$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$projectRoot = Get-ProjectRoot
Import-DotEnv (Join-Path $projectRoot ".env.local")

$port = $env:SCREENING_SERVER_PORT
if (-not $port) { $port = "8080" }
$baseUrl = $env:SCREENING_HEALTHCHECK_BASE_URL
if (-not $baseUrl) { $baseUrl = $env:SCREENING_PUBLIC_BASE_URL }
if (-not $baseUrl) { $baseUrl = "http://127.0.0.1:$port" }

Write-Stage "checking server health: $baseUrl/health"
$health = (Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/health" -TimeoutSec 10).Content
Write-Host "[install] health response: $health"

Write-Stage "checking login page"
Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/login" -TimeoutSec 10 | Out-Null
Write-Host "[install] login page OK"

Write-Stage "checking frontend dist"
if (-not (Test-Path (Join-Path $projectRoot "admin_frontend\dist\index.html"))) {
  throw "frontend dist missing: admin_frontend\dist\index.html"
}

Write-Stage "checking plugin files"
foreach ($rel in @(
  "chrome_extensions\boss_resume_score\manifest.json",
  "chrome_extensions\boss_resume_score\sidepanel.js",
  "chrome_extensions\boss_resume_score\service-worker.js"
)) {
  if (-not (Test-Path (Join-Path $projectRoot $rel))) {
    throw "missing plugin file: $rel"
  }
}
Write-Host "[install] plugin files OK"

Write-Stage "checking database"
if (-not (Test-Path (Join-Path $projectRoot "data\screening.db"))) {
  throw "missing database: data\screening.db"
}
Write-Host "[install] database OK"

Write-Host "[install] all checks passed"
