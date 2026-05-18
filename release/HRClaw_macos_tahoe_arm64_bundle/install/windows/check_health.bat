@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_health.ps1" %*
exit /b %errorlevel%
