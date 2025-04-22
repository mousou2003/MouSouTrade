#!/bin/bash

# Load environment variables from .env file
if [ -f /app/.env ]; then
    export $(grep -v '^#' /app/.env | xargs)
else
    echo "ERROR: .env file not found at /app/.env"
    exit 1
fi

# Debug: Print APP_CODE_PATHS
echo "APP_CODE_PATHS=${APP_CODE_PATHS}"

# Build PYTHONPATH with APP_CODE_PATHS
PYTHONPATH="$PYTHONPATH:/app"
IFS=',' read -r -a paths <<< "$APP_CODE_PATHS"
for path in "${paths[@]}"; do
    # echo "Processing directory: /app/$path"  # Debug: Print each directory
    if [ ! -d "/app/$path" ]; then
        echo "WARNING: Directory /app/$path does not exist"
    else
        PYTHONPATH="$PYTHONPATH:/app/$path"
        # echo "Updated PYTHONPATH=${PYTHONPATH}"  # Debug: Print updated PYTHONPATH
    fi
done

# Export and verify paths
export PYTHONPATH=$PYTHONPATH
export PATH=/app:$PATH

# Debug output
echo "Environment Setup Complete:"
echo "PYTHONPATH=${PYTHONPATH}"
echo "PATH=${PATH}"
env | grep -E '^(AWS_|MOUSOUTRADE_|WEBSITE_PORT|DYNAMODB|PROJECT_NAME)' || echo "No matching environment variables found"
