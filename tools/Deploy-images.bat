@echo off
setlocal

REM Check if .env file exists
if not exist .env (
    echo .env file not found.
    exit /b 1
)

REM Load environment variables from .env file
for /f "tokens=1,2 delims==" %%i in ('type .env') do set %%i=%%j

echo Deploying services...
docker compose --env-file .env -f .\tools\docker-compose-deploy.yml up -d
if %ERRORLEVEL% NEQ 0 (
    echo Failed to deploy services.
    exit /b %ERRORLEVEL%
)

echo Services deployed successfully.

echo Checking if website is accessible...
curl -f http://localhost:%WEBSITE_PORT% >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Website is not accessible at http://localhost:%WEBSITE_PORT%
    echo Please make sure the website is running before pushing images.
    exit /b 1
)

REM Test network connectivity
docker exec -it app ping dynamodb-local -c 4
if %ERRORLEVEL% NEQ 0 (
    echo Network connectivity test failed.
    exit /b %ERRORLEVEL%
)

docker exec -it website ping dynamodb-local -c 4
if %ERRORLEVEL% NEQ 0 (
    echo Network connectivity test failed.
    exit /b %ERRORLEVEL%
)
echo Network connectivity test passed.

endlocal
