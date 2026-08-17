@echo off
REM Entrix CLI launcher script for Windows
REM This script finds and executes the entrix Python module

where entrix >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    entrix %*
    exit /b %ERRORLEVEL%
)

REM Fallback to python -m entrix
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python -m entrix %*
    exit /b %ERRORLEVEL%
)

echo Error: Neither 'entrix' command nor Python found >&2
echo Please install entrix: pip install entrix >&2
exit /b 1