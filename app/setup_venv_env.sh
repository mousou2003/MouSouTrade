#!/bin/bash
ACTIVATE_SCRIPT="/app/venv/bin/activate"

# Ensure venv permissions
chmod -R 755 /app/venv
chmod 644 $ACTIVATE_SCRIPT

# Read from environment and build exports
env | grep -E '^(AWS_|MOUSOUTRADE_|PYTHONPATH|WEBSITE_PORT|DYNAMODB|PROJECT_NAME)' | \
while read -r line; do
    echo "export $line" >> $ACTIVATE_SCRIPT
done

# Ensure the changes are readable
chmod 644 $ACTIVATE_SCRIPT
