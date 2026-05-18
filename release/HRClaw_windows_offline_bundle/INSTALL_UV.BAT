@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_uv.ps1" %*
endlocal
