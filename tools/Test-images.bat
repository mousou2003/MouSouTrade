@echo off
setlocal

REM Check if .env file exists
if not exist .env (
    echo .env file not found.
    exit /b 1
)

REM Load environment variables from .env file
for /f "tokens=1,2 delims==" %%i in ('type .env') do set %%i=%%j

REM Override version for testing
set MOUSOUTRADE_VERSION=latest

echo Stopping any existing containers...
docker compose --env-file .env -f .\tools\docker-compose-deploy.yml down
if %ERRORLEVEL% NEQ 0 (
    echo Failed to stop existing containers.
    exit /b %ERRORLEVEL%
)

echo Deploying latest version of services...
docker compose --env-file .env -f .\tools\docker-compose-deploy.yml up -d
if %ERRORLEVEL% NEQ 0 (
    echo Failed to deploy services.
    exit /b %ERRORLEVEL%
)

echo Waiting for services to start...
timeout /t 10 /nobreak

echo Testing website accessibility...
curl -f http://localhost:%WEBSITE_PORT% >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Website is not accessible at http://localhost:%WEBSITE_PORT%
    docker compose --env-file .env -f .\tools\docker-compose-deploy.yml logs
    exit /b 1
)
echo Website is accessible.

echo Testing network connectivity...
docker exec -it app ping -c 4 dynamodb-local >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo App container cannot connect to dynamodb-local
    exit /b %ERRORLEVEL%
)

docker exec -it website ping -c 4 dynamodb-local >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Website container cannot connect to dynamodb-local
    exit /b %ERRORLEVEL%
)

echo All tests passed successfully.
echo To stop the services, run: docker compose --env-file .env -f .\tools\docker-compose-deploy.yml down

endlocal
