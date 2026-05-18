@echo off
setlocal
if "%SCREENING_BROWSER_CDP_PORT%"=="" set "SCREENING_BROWSER_CDP_PORT=9222"
if "%SCREENING_CHROME_CDP_USER_DATA_DIR%"=="" set "SCREENING_CHROME_CDP_USER_DATA_DIR=%USERPROFILE%\.hrclaw-chrome-cdp-%SCREENING_BROWSER_CDP_PORT%"

set "BUNDLED_CHROME=%~dp0runtime\chrome\chrome-win64\chrome.exe"
set "CHROME_EXE="
if exist "%BUNDLED_CHROME%" set "CHROME_EXE=%BUNDLED_CHROME%"
if "%CHROME_EXE%"=="" if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if "%CHROME_EXE%"=="" if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if "%CHROME_EXE%"=="" if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if not "%CHROME_EXE%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { $r = Invoke-WebRequest -UseBasicParsing -Uri ('http://127.0.0.1:' + $env:SCREENING_BROWSER_CDP_PORT + '/json/version') -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { exit 0 } else { exit 1 } } catch { exit 1 }"
  if errorlevel 1 (
    echo [start] launching Chrome CDP on port %SCREENING_BROWSER_CDP_PORT%
    start "" "%CHROME_EXE%" --remote-debugging-port=%SCREENING_BROWSER_CDP_PORT% --user-data-dir="%SCREENING_CHROME_CDP_USER_DATA_DIR%"
    timeout /t 2 /nobreak >nul
  ) else (
    echo [start] Chrome CDP already available on port %SCREENING_BROWSER_CDP_PORT%
  )
) else (
  echo [start] warning: Chrome executable not found, continue with start_server.ps1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_server.ps1" %*
exit /b %errorlevel%
