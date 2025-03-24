@echo off
setlocal

REM Check if .env file exists
if not exist .env (
    echo .env file not found.
    exit /b 1
)

REM Load environment variables from .env file
for /f "tokens=1,2 delims==" %%i in ('type .env') do set %%i=%%j

echo Building images...
docker compose --env-file .env -f .\tools\docker-compose-build.yml --project-directory . build
if %ERRORLEVEL% NEQ 0 (
    echo Failed to build images.
    exit /b %ERRORLEVEL%
)

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
