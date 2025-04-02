#!/bin/bash
MAX_RETRIES=3
RETRY_DELAY=5

for i in $(seq 1 $MAX_RETRIES); do
    sleep 30
    echo "Attempt $i of $MAX_RETRIES to start application"
    
    if source /app/setup_env.sh; then
        exec python /app/run.py 2>&1 | tee -a /var/log/cron.log
        exit $?
    else
        echo "Setup failed, retrying in $RETRY_DELAY seconds..."
        sleep $RETRY_DELAY
    fi
done

echo "Failed to start after $MAX_RETRIES attempts"
exit 1
