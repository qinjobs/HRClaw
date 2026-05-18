$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$projectRoot = Get-ProjectRoot
$installRoot = Get-InstallRoot
$windowsPackagesDir = Join-Path $installRoot "packages\windows"
$frontendZip = Join-Path $windowsPackagesDir "admin_frontend-dist.zip"
$frontendTgz = Join-Path $installRoot "packages\frontend\admin_frontend-dist.tgz"
$targetDir = Join-Path $projectRoot "admin_frontend"

if (Test-Path $frontendZip) {
  Expand-Archive -Path $frontendZip -DestinationPath $targetDir -Force
  Write-Stage "frontend dist restored from zip to $targetDir"
  return
}

if (Test-Path $frontendTgz) {
  tar -xzf $frontendTgz -C $targetDir
  Write-Stage "frontend dist restored from tgz to $targetDir"
  return
}

throw "missing frontend archive: admin_frontend-dist.zip or admin_frontend-dist.tgz"
