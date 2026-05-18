param(
  [switch]$AllowNetworkFallback
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$projectRoot = Get-ProjectRoot
$installRoot = Get-InstallRoot
$venvPython = Get-VenvPython
$windowsPackagesDir = Join-Path $installRoot "packages\windows"
$wheelhouseDir = Join-Path $windowsPackagesDir "wheelhouse"
$kimiPackageDir = Join-Path $windowsPackagesDir "kimi-cli"
$kimiRequirements = Join-Path $kimiPackageDir "requirements-kimi-cli-win-py312.txt"
$venvScriptsDir = Split-Path -Parent $venvPython
$kimiExe = Join-Path $venvScriptsDir "kimi.exe"

if (-not (Test-Path $venvPython)) {
  throw "missing virtual environment: $venvPython. Please run INSTALL.BAT first."
}

if (-not (Test-Path $kimiPackageDir)) {
  throw "missing kimi-cli package directory: $kimiPackageDir"
}

Set-Location $projectRoot

$pipBaseArgs = @("-m", "pip", "install")
if (-not $AllowNetworkFallback) {
  $pipBaseArgs += "--no-index"
}
if (Test-Path $wheelhouseDir) {
  $pipBaseArgs += @("--find-links", $wheelhouseDir)
}
$pipBaseArgs += @("--find-links", $kimiPackageDir)

Write-Stage "ensuring packaging tools for kimi-cli"
& $venvPython @pipBaseArgs "setuptools" "wheel"
if ($LASTEXITCODE -ne 0) {
  throw "prepare packaging tools for kimi-cli failed with exit code $LASTEXITCODE"
}

if (Test-Path $kimiRequirements) {
  Write-Stage "installing kimi-cli runtime dependency set"
  & $venvPython @pipBaseArgs "-r" $kimiRequirements
  if ($LASTEXITCODE -ne 0) {
    throw "installing kimi-cli runtime dependency set failed with exit code $LASTEXITCODE"
  }
} else {
  Write-Stage "requirements file not found, installing kimi-cli directly"
}

Write-Stage "installing kimi-cli"
# Install the wheel without resolving its optional MCP/OpenAPI dependency chain.
# The Windows runtime only needs the CLI bridge for `kimi --print`.
& $venvPython @pipBaseArgs "--no-deps" "kimi-cli==1.35.0"
if ($LASTEXITCODE -ne 0) {
  throw "installing kimi-cli failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $kimiExe)) {
  throw "kimi-cli install succeeded but executable not found: $kimiExe"
}

Write-Host ""
Write-Host "kimi-cli ready: $kimiExe"
Write-Host "Try: `"$kimiExe --version`""
