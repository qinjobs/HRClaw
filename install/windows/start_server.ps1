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
$chromeCdpPort = $env:SCREENING_BROWSER_CDP_PORT
if (-not $chromeCdpPort) { $chromeCdpPort = "9222" }
$chromeProfileDir = $env:SCREENING_CHROME_CDP_USER_DATA_DIR
if (-not $chromeProfileDir) { $chromeProfileDir = Join-Path $env:USERPROFILE ".hrclaw-chrome-cdp-$chromeCdpPort" }
$bundledChromeExe = Join-Path $installRoot "runtime\chrome\chrome-win64\chrome.exe"

function Test-ChromeCdpReady {
  param([Parameter(Mandatory = $true)][string]$Port)
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 2
    return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
  } catch {
    return $false
  }
}

function Resolve-ChromeExecutable {
  param([Parameter(Mandatory = $true)][string]$BundledChromeExe)

  if (Test-Path $BundledChromeExe) {
    return $BundledChromeExe
  }

  $candidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe"),
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe")
  )

  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path $candidate)) {
      return $candidate
    }
  }

  try {
    $command = Get-Command "chrome" -ErrorAction Stop
    if ($command -and $command.Source) {
      return $command.Source
    }
  } catch {
    # ignore
  }

  return $null
}

function Ensure-ChromeCdp {
  param(
    [Parameter(Mandatory = $true)][string]$Port,
    [Parameter(Mandatory = $true)][string]$ProfileDir,
    [Parameter(Mandatory = $true)][string]$BundledChromeExe
  )

  if (Test-ChromeCdpReady -Port $Port) {
    Write-Stage "Chrome CDP already available on :$Port"
    return
  }

  $chromeExe = Resolve-ChromeExecutable -BundledChromeExe $BundledChromeExe
  if (-not $chromeExe) {
    Write-Stage "warning: Chrome not found, skipped auto-launch for CDP :$Port"
    return
  }

  Ensure-Directory $ProfileDir
  Write-Stage "launching Chrome with CDP port $Port"
  Start-Process -FilePath $chromeExe -ArgumentList @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$ProfileDir"
  ) | Out-Null

  for ($i = 0; $i -lt 20; $i++) {
    if (Test-ChromeCdpReady -Port $Port) {
      Write-Stage "Chrome CDP ready: http://127.0.0.1:$Port"
      return
    }
    Start-Sleep -Seconds 1
  }

  Write-Stage "warning: Chrome opened but CDP port $Port is not ready yet"
}

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

Ensure-ChromeCdp -Port $chromeCdpPort -ProfileDir $chromeProfileDir -BundledChromeExe $bundledChromeExe

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
if (-not $env:SCREENING_BROWSER_CDP_URL) {
  $env:SCREENING_BROWSER_CDP_URL = "http://127.0.0.1:$chromeCdpPort"
}
$env:SCREENING_BROWSER_CDP_PORT = "$chromeCdpPort"
$env:SCREENING_BROWSER_CDP_REQUIRED = "true"
if (-not $env:SCREENING_BROWSER_FALLBACK_CDP_PORTS) {
  $env:SCREENING_BROWSER_FALLBACK_CDP_PORTS = "$chromeCdpPort"
}
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
