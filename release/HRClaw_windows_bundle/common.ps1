Set-StrictMode -Version Latest

function Find-AncestorWithPaths {
  param(
    [Parameter(Mandatory = $true)][string]$StartPath,
    [Parameter(Mandatory = $true)][string[]]$RelativePaths
  )

  $current = $StartPath
  if (-not (Test-Path $current)) {
    $current = Split-Path -Parent $current
  }

  while ($current) {
    foreach ($relativePath in $RelativePaths) {
      $candidate = Join-Path $current $relativePath
      if (Test-Path $candidate) {
        return $current
      }
    }

    $parent = Split-Path -Parent $current
    if (-not $parent -or $parent -eq $current) {
      break
    }
    $current = $parent
  }

  return $null
}

function Get-ProjectRoot {
  $resolved = Find-AncestorWithPaths -StartPath $PSScriptRoot -RelativePaths @(
    "pyproject.toml",
    "src\screening\server.py"
  )
  if ($resolved) {
    return $resolved
  }
  throw "cannot locate project root. Please extract the full project folder so pyproject.toml and src\screening\server.py are available."
}

function Get-InstallRoot {
  $resolved = Find-AncestorWithPaths -StartPath $PSScriptRoot -RelativePaths @(
    "packages\windows\admin_frontend-dist.zip",
    "packages\windows\.env.local.example",
    "packages\frontend\admin_frontend-dist.tgz"
  )
  if ($resolved) {
    return $resolved
  }
  throw "cannot locate install packages. Please extract the full project folder so packages\windows is available."
}

function Write-Stage {
  param([Parameter(Mandatory = $true)][string]$Message)
  Write-Host "[install] $Message" -ForegroundColor Cyan
}

function Ensure-Directory {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path $Path)) {
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
  }
}

function Clear-DirectoryContents {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (Test-Path $Path) {
    Get-ChildItem -Force -LiteralPath $Path -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  }
}

function Reset-WindowsRuntimeData {
  param([Parameter(Mandatory = $true)][string]$ProjectRoot)
  Clear-DirectoryContents (Join-Path $ProjectRoot "data")

  foreach ($relativePath in @(
    "data\screening.db",
    "data\hr_screening.db",
    "data\server.pid",
    "data\api_cookie.txt",
    "data\auth\boss_storage_state.json",
    "data\auth\boss_session_meta.json"
  )) {
    $fullPath = Join-Path $ProjectRoot $relativePath
    if (Test-Path $fullPath) {
      Remove-Item $fullPath -Force -ErrorAction SilentlyContinue
    }
  }

  foreach ($dir in @(
    "data\auth",
    "data\logs",
    "data\pids",
    "data\qdrant",
    "data\qdrant_search",
    "data\imports",
    "data\resumes",
    "data\runs",
    "data\screenshots",
    "snapshots\tmp"
  )) {
    Clear-DirectoryContents (Join-Path $ProjectRoot $dir)
  }
}

function Import-DotEnv {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path $Path)) {
    return
  }

  Get-Content $Path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
      return
    }
    $parts = $line.Split("=", 2)
    if ($parts.Count -ne 2) {
      return
    }
    $key = $parts[0].Trim()
    $value = $parts[1].Trim()
    if ($key) {
      [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
  }
}

function Get-VenvPython {
  return (Join-Path (Get-ProjectRoot) ".venv\Scripts\python.exe")
}

function Get-ManagedPython {
  return (Join-Path (Get-InstallRoot) "runtime\python\python.exe")
}

function Get-PythonInstallerUrl {
  return "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"
}

function Test-Url {
  param([Parameter(Mandatory = $true)][string]$Url)
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Method Head -Uri $Url -TimeoutSec 10
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
  } catch {
    return $false
  }
}

function Wait-Health {
  param(
    [Parameter(Mandatory = $true)][string]$BaseUrl,
    [int]$TimeoutSeconds = 30
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $payload = (Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/health" -TimeoutSec 5).Content
      if ($payload) {
        return $true
      }
    } catch {
      Start-Sleep -Seconds 1
      continue
    }
    Start-Sleep -Seconds 1
  }
  return $false
}
