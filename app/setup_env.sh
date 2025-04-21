#!/bin/bash

# Redirect all output to /var/log/cron.log
exec >> /var/log/cron.log 2>&1

# Required environment variables
REQUIRED_VARS=(
    "AWS_PROFILE"
    "AWS_ACCESS_KEY_ID"
    "AWS_SECRET_ACCESS_KEY"
    "AWS_DEFAULT_REGION"
    "MOUSOUTRADE_CONFIG_FILE"
    "MOUSOUTRADE_STAGE"
    "APP_CODE_PATHS"
)

# Check required variables
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "ERROR: Required environment variable $var is not set"
        exit 1
    fi
done

# Build PYTHONPATH with APP_CODE_PATHS
PYTHONPATH="$PYTHONPATH:/app"
for path in ${APP_CODE_PATHS}; do
    if [ ! -d "/app/$path" ]; then
        echo "WARNING: Directory /app/$path does not exist"
    fi
    PYTHONPATH="$PYTHONPATH:/app/$path"
done

# Export and verify paths
export PYTHONPATH=$PYTHONPATH
export PATH=/app:$PATH

# Debug output
echo "Environment Setup Complete:"
echo "PYTHONPATH=$PYTHONPATH"
echo "PATH=$PATH"
env | grep -E '^(AWS_|MOUSOUTRADE_|WEBSITE_PORT|DYNAMODB|PROJECT_NAME)' || echo "No matching environment variables found"
