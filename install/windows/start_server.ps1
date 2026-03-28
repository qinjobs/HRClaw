$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$projectRoot = Get-ProjectRoot
$installRoot = Get-InstallRoot
$envFile = Join-Path $projectRoot ".env.local"
Import-DotEnv $envFile
$env:SCREENING_WEB_USERNAME = "admin"
$env:SCREENING_WEB_PASSWORD = "admin"
$env:SCREENING_SEED_BUILTIN_SCORECARDS = "false"
$venvPython = Get-VenvPython
$serverHost = $env:SCREENING_SERVER_HOST
if (-not $serverHost) { $serverHost = "127.0.0.1" }
$serverPort = $env:SCREENING_SERVER_PORT
if (-not $serverPort) { $serverPort = "8080" }
$baseUrl = $env:SCREENING_PUBLIC_BASE_URL
if (-not $baseUrl) { $baseUrl = "http://127.0.0.1:$serverPort" }

if (-not (Test-Path $venvPython)) {
  throw "Virtual environment not found. Run install.ps1 first."
}

Ensure-Directory (Join-Path $projectRoot "data\logs")
Ensure-Directory (Join-Path $projectRoot "data\pids")
Ensure-Directory (Join-Path $projectRoot "data\runs")
$logFile = Join-Path $projectRoot "data\logs\phase1_server.log"
$errorLogFile = Join-Path $projectRoot "data\logs\phase1_server.err.log"
$pidFile = Join-Path $projectRoot "data\pids\phase1_server.pid"
$launcherFile = Join-Path $projectRoot "data\runs\phase1_server_bootstrap.py"

if (Test-Path $pidFile) {
  $existingPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($existingPid) {
    try {
      Get-Process -Id ([int]$existingPid) -ErrorAction Stop | Out-Null
      Write-Stage "server already running: pid=$existingPid"
      Write-Stage "access url: $baseUrl"
      return
    } catch {
      Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
  }
}

$launcherContent = @"
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.screening.server import run
run(host='$serverHost', port=$serverPort)
"@
[System.IO.File]::WriteAllText($launcherFile, $launcherContent, [System.Text.Encoding]::ASCII)
Write-Stage "starting server bind: http://${serverHost}:$serverPort"
$proc = Start-Process -FilePath $venvPython -ArgumentList @($launcherFile) -WorkingDirectory $projectRoot -RedirectStandardOutput $logFile -RedirectStandardError $errorLogFile -PassThru -WindowStyle Hidden
$proc.Id | Set-Content $pidFile
Write-Stage "server pid: $($proc.Id)"
if (Wait-Health -BaseUrl $baseUrl -TimeoutSeconds 45) {
  Write-Stage "server is healthy"
  Write-Stage "access url: $baseUrl"
} else {
  Write-Stage "server did not become healthy in time"
  Write-Host "Please check $logFile and $errorLogFile"
  exit 1
}
