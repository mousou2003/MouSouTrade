@echo off
setlocal

REM Check if .env file exists
if not exist .env (
    echo .env file not found.
    exit /b 1
)

REM Load environment variables from .env file
for /f "tokens=1,2 delims==" %%i in ('type .env') do set %%i=%%j

REM Set IMAGE_PUSH_ARG variables
set WEBSITE_IMAGE_PUSH_ARG=%DOCKERHUB_USERNAME%/%WEBSITE_IMAGE_NAME%
set APP_IMAGE_PUSH_ARG=%DOCKERHUB_USERNAME%/%APP_IMAGE_NAME%

echo Check if website image exists
docker image inspect "%WEBSITE_IMAGE_PUSH_ARG%:latest" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Image %WEBSITE_IMAGE_NAME%:latest not found.
    exit /b %ERRORLEVEL%
)

echo Pushing website image...
docker push "%WEBSITE_IMAGE_PUSH_ARG%:latest"
if %ERRORLEVEL% NEQ 0 (
    echo Failed to push website image.
    exit /b %ERRORLEVEL%
)

echo Tagging %WEBSITE_IMAGE_NAME
docker tag "%WEBSITE_IMAGE_PUSH_ARG%:latest" "%WEBSITE_IMAGE_PUSH_ARG%:%MOUSOUTRADE_VERSION%"
if %ERRORLEVEL% NEQ 0 (
    echo Failed to tag website image.
    exit /b %ERRORLEVEL%
)

echo Pushing tagged website image...
docker push "%WEBSITE_IMAGE_PUSH_ARG%:%MOUSOUTRADE_VERSION%"
if %ERRORLEVEL% NEQ 0 (
    echo Failed to push tagged website image.
    exit /b %ERRORLEVEL%
)

echo Check if app image exists
docker image inspect "%APP_IMAGE_PUSH_ARG%:latest" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Image %APP_IMAGE_NAME%:latest not found.
    exit /b %ERRORLEVEL%
)

echo Pushing app image...
docker push "%APP_IMAGE_PUSH_ARG%:latest"
if %ERRORLEVEL% NEQ 0 (
    echo Failed to push app image.
    exit /b %ERRORLEVEL%
)

echo Tagging %APP_IMAGE_NAME
docker tag "%APP_IMAGE_PUSH_ARG%:latest" "%APP_IMAGE_PUSH_ARG%:%MOUSOUTRADE_VERSION%"
if %ERRORLEVEL% NEQ 0 (
    echo Failed to tag app image.
    exit /b %ERRORLEVEL%
)

echo Pushing tagged app image...
docker push "%APP_IMAGE_PUSH_ARG%:%MOUSOUTRADE_VERSION%"
if %ERRORLEVEL% NEQ 0 (
    echo Failed to push tagged app image.
    exit /b %ERRORLEVEL%
)

endlocal