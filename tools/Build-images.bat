@echo off
setlocal EnableDelayedExpansion

REM Check if .env file exists
if not exist .env (
    echo .env file not found.
    exit /b 1
)

REM Load environment variables from .env file
for /f "tokens=1,* delims==" %%i in ('type .env') do (
    if "%%i"=="APP_CODE_PATHS" (
        set APP_CODE_PATHS=%%j
    ) else (
        set %%i=%%j
    )
)

REM Create staging directory
echo APP_CODE_PATHS=%APP_CODE_PATHS%
echo Creating staging directory...
set STAGING_DIR=.\build\staging
if exist %STAGING_DIR% rmdir /s /q %STAGING_DIR%
mkdir %STAGING_DIR%

REM Copy each directory separately
set "dirs=%APP_CODE_PATHS%"
:process_dirs
for /f "tokens=1*" %%a in ("%dirs%") do (
    if exist ".\%%a" (
        echo Copying .\%%a to staging...
        xcopy ".\%%a" "%STAGING_DIR%\%%a\" /E /I /Y
    ) else (
        echo Error: Directory .\%%a not found
        exit /b 1
    )
    set "dirs=%%b"
)
if defined dirs goto :process_dirs
pause
echo Building images...
set DOCKER_BUILDKIT=1
docker compose --env-file .env -f .\tools\docker-compose-build.yml --project-directory . build
if %ERRORLEVEL% NEQ 0 (
    echo Failed to build images.
    exit /b %ERRORLEVEL%
)

REM Clean up staging directory
rmdir /s /q %STAGING_DIR%

echo Images built successfully.

REM Verify images were created
echo Verifying images...
docker image inspect "%DOCKERHUB_USERNAME%/%WEBSITE_IMAGE_NAME%:latest" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Website image build failed.
    exit /b %ERRORLEVEL%
)

docker image inspect "%DOCKERHUB_USERNAME%/%APP_IMAGE_NAME%:latest" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo App image build failed.
    exit /b %ERRORLEVEL%
)

echo All images built and verified successfully.
endlocal
