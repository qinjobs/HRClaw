$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$projectRoot = Get-ProjectRoot
$pidFile = Join-Path $projectRoot "data\pids\phase1_server.pid"

if (-not (Test-Path $pidFile)) {
  Write-Stage "server pid file not found"
  exit 0
}

$pidValue = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $pidValue) {
  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
  Write-Stage "server pid file was empty"
  exit 0
}

try {
  Stop-Process -Id ([int]$pidValue) -Force -ErrorAction Stop
  Write-Stage "server stopped: pid=$pidValue"
} catch {
  Write-Stage "server process not running: pid=$pidValue"
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
