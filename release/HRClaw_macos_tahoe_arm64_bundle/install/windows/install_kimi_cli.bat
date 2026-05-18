@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_kimi_cli.ps1" %*
endlocal
