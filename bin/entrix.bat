@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0entrix-bootstrap.ps1" %*
exit /b %ERRORLEVEL%
