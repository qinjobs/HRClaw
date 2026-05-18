@echo off
setlocal
set "LOG_DIR=%~dp0data\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "SERVER_LOG=%LOG_DIR%\server.log"
echo [start] ==== START_SERVER.BAT %date% %time% ====>> "%SERVER_LOG%"
echo [start] working dir: %~dp0>> "%SERVER_LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_server.ps1" %* >> "%SERVER_LOG%" 2>&1
endlocal & exit /b %errorlevel%
