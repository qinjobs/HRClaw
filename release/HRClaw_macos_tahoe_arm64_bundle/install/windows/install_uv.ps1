param(
  [switch]$AddToUserPath
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$installRoot = Get-InstallRoot
$uvPackageDir = Join-Path $installRoot "packages\windows\uv"
$uvZip = Join-Path $uvPackageDir "uv-x86_64-pc-windows-msvc.zip"
$uvSha256 = Join-Path $uvPackageDir "uv-x86_64-pc-windows-msvc.zip.sha256"
$uvRuntimeDir = Join-Path $installRoot "runtime\uv"
$uvExe = $null

if (-not (Test-Path $uvZip)) {
  throw "missing bundled uv package: $uvZip"
}

if (Test-Path $uvSha256) {
  $expectedHash = ((Get-Content $uvSha256 -Raw).Trim().Split(" ", 2)[0]).ToLowerInvariant()
  if ($expectedHash) {
    $actualHash = (Get-FileHash -Algorithm SHA256 -Path $uvZip).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
      throw "uv package hash mismatch. expected=$expectedHash actual=$actualHash"
    }
  }
}

Write-Stage "restoring uv runtime"
Ensure-Directory $uvRuntimeDir
Expand-Archive -Path $uvZip -DestinationPath $uvRuntimeDir -Force

if (Test-Path (Join-Path $uvRuntimeDir "uv.exe")) {
  $uvExe = Join-Path $uvRuntimeDir "uv.exe"
} else {
  $candidate = Get-ChildItem -Path $uvRuntimeDir -Recurse -Filter "uv.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($candidate) {
    $uvExe = $candidate.FullName
  }
}

if (-not $uvExe -or -not (Test-Path $uvExe)) {
  throw "uv runtime restore failed: uv.exe not found under $uvRuntimeDir"
}

if ($AddToUserPath) {
  $targetPath = Split-Path -Parent $uvExe
  $existingUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $pathParts = @()
  if ($existingUserPath) {
    $pathParts = $existingUserPath.Split(";") | Where-Object { $_ -and $_.Trim() }
  }
  if (-not ($pathParts -contains $targetPath)) {
    $updatedPath = @($pathParts + $targetPath) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $updatedPath, "User")
    Write-Stage "added uv path to user PATH: $targetPath"
  } else {
    Write-Stage "uv path already exists in user PATH: $targetPath"
  }
}

Write-Host ""
Write-Host "uv ready: $uvExe"
Write-Host "Try: `"$uvExe --version`""
