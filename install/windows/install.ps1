param(
  [switch]$InstallSearchDeps
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$projectRoot = Get-ProjectRoot
$installRoot = Get-InstallRoot
$pythonDir = Join-Path $installRoot "runtime\python"
$pythonExe = Join-Path $pythonDir "python.exe"
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Get-VenvPython
$packagesDir = Join-Path $installRoot "packages"
$windowsPackagesDir = Join-Path $packagesDir "windows"
$wheelhouseDir = Join-Path $windowsPackagesDir "wheelhouse"
$frontendZip = Join-Path $windowsPackagesDir "admin_frontend-dist.zip"
$frontendTgz = Join-Path $packagesDir "frontend\admin_frontend-dist.tgz"
$envExample = Join-Path $windowsPackagesDir ".env.local.example"
$envTarget = Join-Path $projectRoot ".env.local"

Set-Location $projectRoot
Write-Stage "project root: $projectRoot"

Reset-WindowsRuntimeData -ProjectRoot $projectRoot
Ensure-Directory $pythonDir
Ensure-Directory (Join-Path $projectRoot "data\auth")
Ensure-Directory (Join-Path $projectRoot "data\logs")
Ensure-Directory (Join-Path $projectRoot "data\pids")
Ensure-Directory (Join-Path $projectRoot "data\qdrant_search")
Ensure-Directory (Join-Path $projectRoot "data\resumes")
Ensure-Directory (Join-Path $projectRoot "data\runs")
Ensure-Directory (Join-Path $projectRoot "data\screenshots")
Ensure-Directory (Join-Path $projectRoot "data\imports")
Ensure-Directory (Join-Path $projectRoot "snapshots\tmp")

if (-not (Test-Path $pythonExe)) {
  Write-Stage "local Python runtime not found, preparing installer..."
  $bundledInstaller = Join-Path $windowsPackagesDir "python-3.12.9-amd64.exe"
  if (-not (Test-Path $bundledInstaller)) {
    $downloadUrl = Get-PythonInstallerUrl
    $downloadDest = Join-Path $env:TEMP "python-3.12.9-amd64.exe"
    Write-Stage "downloading Python 3.12 installer from official source"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $downloadDest
    $bundledInstaller = $downloadDest
  }

  Write-Stage "installing Python into $pythonDir"
  $installerArgs = @(
    "/quiet"
    "InstallAllUsers=0"
    "PrependPath=0"
    "Include_test=0"
    "Include_pip=1"
    "SimpleInstall=1"
    "TargetDir=$pythonDir"
  )
  Start-Process -FilePath $bundledInstaller -ArgumentList $installerArgs -Wait -NoNewWindow
}

if (-not (Test-Path $pythonExe)) {
  throw "Python runtime install failed: $pythonExe not found."
}

Write-Stage "creating virtual environment"
& $pythonExe -m venv $venvDir
if (-not (Test-Path $venvPython)) {
  throw "virtual environment was not created correctly: $venvPython"
}

$pipBaseArgs = @("-m", "pip", "install")
if ((Test-Path $wheelhouseDir) -and (Get-ChildItem $wheelhouseDir -Filter "*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1)) {
  Write-Stage "using local wheelhouse: $wheelhouseDir"
  $pipBaseArgs += @("--find-links", $wheelhouseDir)
}

Write-Stage "upgrading packaging tools"
& $venvPython -m pip install --upgrade pip setuptools wheel

Write-Stage "installing project in editable mode"
& $venvPython -m pip install -e $projectRoot

Write-Stage "installing phase 1 dependencies"
& $venvPython @pipBaseArgs -r (Join-Path $packagesDir "python\requirements-phase1.txt")

Write-Stage "installing OCR dependencies"
try {
  & $venvPython @pipBaseArgs "paddlepaddle"
  & $venvPython @pipBaseArgs -r (Join-Path $packagesDir "python\requirements-phase2-ocr.txt")
} catch {
  Write-Host "[install] OCR dependencies failed, continuing without OCR: $($_.Exception.Message)" -ForegroundColor Yellow
}

if ($InstallSearchDeps) {
  Write-Stage "installing optional search dependencies"
  try {
    & $venvPython @pipBaseArgs -r (Join-Path $packagesDir "python\requirements-phase2-search-optional.txt")
  } catch {
    Write-Host "[install] optional search dependencies failed, continuing: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

Write-Stage "installing Playwright Chromium"
& $venvPython -m playwright install chromium

if (-not (Test-Path $envTarget) -and (Test-Path $envExample)) {
  Copy-Item $envExample $envTarget
  Write-Stage "created default .env.local"
}

if (-not (Test-Path $envTarget)) {
  throw "missing .env.local after installation"
}

Import-DotEnv $envTarget

if (Test-Path $frontendZip) {
  Write-Stage "restoring frontend dist from Windows zip package"
  Expand-Archive -Path $frontendZip -DestinationPath (Join-Path $projectRoot "admin_frontend") -Force
} elseif (Test-Path $frontendTgz) {
  Write-Stage "restoring frontend dist from existing tgz package"
  tar -xzf $frontendTgz -C (Join-Path $projectRoot "admin_frontend")
}

Write-Stage "starting local server"
& (Join-Path $PSScriptRoot "start_server.ps1")

$baseUrl = $env:SCREENING_PUBLIC_BASE_URL
if (-not $baseUrl) {
  $baseUrl = "http://127.0.0.1:8080"
}

if (Wait-Health -BaseUrl $baseUrl -TimeoutSeconds 45) {
  Write-Stage "installation completed"
  Write-Host ""
  Write-Host "Login: $baseUrl/login"
  Write-Host "JD评分卡: $baseUrl/hr/phase2"
  Write-Host "简历导入: $baseUrl/hr/resume-imports"
  try {
    Start-Process "$baseUrl/login"
  } catch {
    # ignore
  }
} else {
  Write-Stage "server did not become healthy in time"
  Write-Host "Please check the server logs under data\logs\phase1_server.log and data\logs\phase1_server.err.log"
  exit 1
}
