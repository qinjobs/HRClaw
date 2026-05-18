param(
  [switch]$InstallSearchDeps,
  [switch]$AllowNetworkFallback
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
$kimiPackageDir = Join-Path $windowsPackagesDir "kimi-cli"
$frontendZip = Join-Path $windowsPackagesDir "admin_frontend-dist.zip"
$frontendTgz = Join-Path $packagesDir "frontend\admin_frontend-dist.tgz"
$chromeZip = Join-Path $windowsPackagesDir "chrome-win64.zip"
$chromeRuntimeDir = Join-Path $installRoot "runtime\chrome"
$chromeExe = Join-Path $chromeRuntimeDir "chrome-win64\chrome.exe"
$envExample = Join-Path $windowsPackagesDir ".env.local.example"
$envTarget = Join-Path $projectRoot ".env.local"
$bootstrapPythonExe = $null

function Invoke-CheckedProcess {
  param(
    [Parameter(Mandatory = $true)][string]$Description,
    [Parameter(Mandatory = $true)][scriptblock]$Command
  )
  Write-Stage $Description
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Description failed with exit code $LASTEXITCODE"
  }
}

function Invoke-NativeQuiet {
  param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string[]]$Arguments
  )
  $previous = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $PythonExe @Arguments *> $null
    return $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previous
  }
}

function Test-PipAvailable {
  param([Parameter(Mandatory = $true)][string]$PythonExe)
  $exitCode = Invoke-NativeQuiet -PythonExe $PythonExe -Arguments @("-m", "pip", "--version")
  return ($exitCode -eq 0)
}

function Ensure-PythonPip {
  param([Parameter(Mandatory = $true)][string]$PythonExe)

  if (Test-PipAvailable -PythonExe $PythonExe) {
    return
  }

  Write-Stage "pip not found in Python runtime, trying ensurepip"
  $null = Invoke-NativeQuiet -PythonExe $PythonExe -Arguments @("-m", "ensurepip", "--upgrade")
  if (Test-PipAvailable -PythonExe $PythonExe) {
    return
  }

  throw "Python runtime does not provide pip: $PythonExe"
}

function Ensure-Venv {
  param(
    [Parameter(Mandatory = $true)][string]$BootstrapPythonExe,
    [Parameter(Mandatory = $true)][string]$VenvDir,
    [Parameter(Mandatory = $true)][string]$VenvPythonExe
  )

  if (Test-Path $VenvPythonExe) {
    Write-Stage "reusing existing virtual environment: $VenvDir"
    return
  }

  if (Test-Path $VenvDir) {
    Write-Stage "resetting existing virtual environment: $VenvDir"
    try {
      Remove-Item -LiteralPath $VenvDir -Recurse -Force -ErrorAction Stop
    } catch {
      throw "cannot reset virtual environment at $VenvDir. Close terminals/VSCode/antivirus locks, delete this folder manually, then rerun install. detail: $($_.Exception.Message)"
    }
  }

  Write-Stage "creating virtual environment"
  & $BootstrapPythonExe -m venv $VenvDir
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPythonExe)) {
    throw "virtual environment was not created correctly: $VenvPythonExe"
  }
}

function Ensure-VenvPip {
  param(
    [Parameter(Mandatory = $true)][string]$VenvPythonExe,
    [Parameter(Mandatory = $true)][string]$BootstrapPythonExe
  )

  if (Test-PipAvailable -PythonExe $VenvPythonExe) {
    return
  }

  Write-Stage "pip not found in virtual environment, trying ensurepip"
  $null = Invoke-NativeQuiet -PythonExe $VenvPythonExe -Arguments @("-m", "ensurepip", "--upgrade")
  if (Test-PipAvailable -PythonExe $VenvPythonExe) {
    return
  }

  Write-Stage "ensurepip did not provide pip, trying host pip bootstrap"
  Ensure-PythonPip -PythonExe $BootstrapPythonExe
  $null = Invoke-NativeQuiet -PythonExe $BootstrapPythonExe -Arguments @(
    "-m",
    "pip",
    "--python",
    $VenvPythonExe,
    "install",
    "--upgrade",
    "pip",
    "setuptools",
    "wheel"
  )
  if (Test-PipAvailable -PythonExe $VenvPythonExe) {
    return
  }

  throw "virtual environment pip bootstrap failed. Please verify Python 3.12 includes ensurepip/pip, then rerun install."
}

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

$bootstrapPythonExe = if (Test-Path $pythonExe) { $pythonExe } else { $null }
if (-not $bootstrapPythonExe) {
  $resolvedSystemPython = Resolve-SystemPython312
  if ($resolvedSystemPython) {
    Write-Stage "reusing existing system Python 3.12: $resolvedSystemPython"
    $bootstrapPythonExe = $resolvedSystemPython
  }
}

if (-not $bootstrapPythonExe) {
  Write-Stage "local Python runtime not found, preparing bundled installer..."
  $bundledInstaller = Join-Path $windowsPackagesDir "python-3.12.9-amd64.exe"
  if (-not (Test-Path $bundledInstaller)) {
    if (-not $AllowNetworkFallback) {
      throw "missing bundled Python installer: $bundledInstaller. Offline install requires this file."
    }
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
  $installerProcess = Start-Process -FilePath $bundledInstaller -ArgumentList $installerArgs -Wait -PassThru -NoNewWindow
  if ($installerProcess.ExitCode -eq 1638) {
    $resolvedSystemPython = Resolve-SystemPython312
    if ($resolvedSystemPython) {
      Write-Stage "bundled installer reported existing Python; reusing existing system Python 3.12: $resolvedSystemPython"
      $bootstrapPythonExe = $resolvedSystemPython
    } else {
      throw "Python installer exited with code 1638 and no usable system Python 3.12 was found."
    }
  } elseif ($installerProcess.ExitCode -ne 0) {
    throw "Python installer exited with code $($installerProcess.ExitCode)."
  } elseif (Test-Path $pythonExe) {
    $bootstrapPythonExe = $pythonExe
  }
}

if (-not $bootstrapPythonExe -or -not (Test-Path $bootstrapPythonExe)) {
  throw "Python runtime install failed: no usable Python 3.12 executable was found."
}

Ensure-PythonPip -PythonExe $bootstrapPythonExe
Ensure-Venv -BootstrapPythonExe $bootstrapPythonExe -VenvDir $venvDir -VenvPythonExe $venvPython
Ensure-VenvPip -VenvPythonExe $venvPython -BootstrapPythonExe $bootstrapPythonExe

$pipBaseArgs = @("-m", "pip", "install")
$usingLocalWheelhouse = (Test-Path $wheelhouseDir) -and (Get-ChildItem $wheelhouseDir -Filter "*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1)
if ($usingLocalWheelhouse) {
  Write-Stage "using local wheelhouse: $wheelhouseDir"
  $pipBaseArgs += @("--no-index", "--find-links", $wheelhouseDir)
  if (Test-Path $kimiPackageDir) {
    Write-Stage "using secondary offline wheel source: $kimiPackageDir"
    $pipBaseArgs += @("--find-links", $kimiPackageDir)
  }
} elseif (-not $AllowNetworkFallback) {
  throw "offline wheelhouse is missing: $wheelhouseDir. Offline install cannot continue."
}

if ($usingLocalWheelhouse) {
  $localWheelPackage = Get-ChildItem $wheelhouseDir -Filter "wheel-*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($localWheelPackage) {
    Invoke-CheckedProcess -Description "ensuring local setuptools/wheel" -Command {
      & $venvPython @pipBaseArgs "setuptools" "wheel"
    }
  } else {
    Write-Stage "local wheel package not found; continuing with setuptools only"
    Invoke-CheckedProcess -Description "ensuring local setuptools" -Command {
      & $venvPython @pipBaseArgs "setuptools"
    }
  }
} else {
  Invoke-CheckedProcess -Description "upgrading packaging tools" -Command {
    & $venvPython -m pip install --upgrade pip setuptools wheel
  }
}

Invoke-CheckedProcess -Description "installing project in editable mode" -Command {
  & $venvPython -m pip install --no-deps -e $projectRoot
}

Invoke-CheckedProcess -Description "installing phase 1 dependencies" -Command {
  & $venvPython @pipBaseArgs -r (Join-Path $packagesDir "python\requirements-phase1.txt")
}

Write-Stage "installing OCR dependencies"
try {
  Invoke-CheckedProcess -Description "installing paddlepaddle runtime" -Command {
    & $venvPython @pipBaseArgs "paddlepaddle"
  }
  Invoke-CheckedProcess -Description "installing OCR dependency set" -Command {
    & $venvPython @pipBaseArgs -r (Join-Path $packagesDir "python\requirements-phase2-ocr.txt")
  }
} catch {
  Write-Host "[install] OCR dependencies failed, continuing without OCR: $($_.Exception.Message)" -ForegroundColor Yellow
}

if ($InstallSearchDeps) {
  Write-Stage "installing optional search dependencies"
  try {
    Invoke-CheckedProcess -Description "installing optional search dependency set" -Command {
      & $venvPython @pipBaseArgs -r (Join-Path $packagesDir "python\requirements-phase2-search-optional.txt")
    }
  } catch {
    Write-Host "[install] optional search dependencies failed, continuing: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

if (Test-Path $chromeZip) {
  Write-Stage "restoring bundled Chrome runtime"
  Ensure-Directory $chromeRuntimeDir
  Expand-Archive -Path $chromeZip -DestinationPath $chromeRuntimeDir -Force
} elseif (-not (Test-Path $chromeExe)) {
  if ($AllowNetworkFallback) {
    Invoke-CheckedProcess -Description "installing Playwright Chromium from network fallback" -Command {
      & $venvPython -m playwright install chromium
    }
  } else {
    throw "missing bundled Chrome package: $chromeZip. Offline install requires this file."
  }
}

if ((-not (Test-Path $chromeExe)) -and (-not $AllowNetworkFallback)) {
  throw "offline Chrome executable missing: $chromeExe"
}

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

$baseUrl = $env:SCREENING_PUBLIC_BASE_URL
if (-not $baseUrl) {
  $baseUrl = "http://127.0.0.1:8080"
}

Write-Stage "installation completed"
Write-Host ""
Write-Host "默认不会自动启动服务。"
Write-Host "请手工执行 START_SERVER.BAT 启动后台服务。"
Write-Host ""
Write-Host "启动后访问："
Write-Host "Login: $baseUrl/login"
Write-Host "JD评分卡: $baseUrl/hr/phase2"
Write-Host "简历导入: $baseUrl/hr/resume-imports"
