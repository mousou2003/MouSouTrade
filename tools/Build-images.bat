@echo off
setlocal EnableDelayedExpansion

REM Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python is not installed or not added to PATH.
    exit /b 1
)

REM Call the Python script
python .\tools\Build-images.py
if %ERRORLEVEL% NEQ 0 (
    echo Python script execution failed.
    exit /b %ERRORLEVEL%
)

endlocal
