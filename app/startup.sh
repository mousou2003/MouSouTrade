#!/bin/bash
MAX_RETRIES=3
RETRY_DELAY=5

run_app() {
    if source /app/setup_env.sh; then
        python /app/run.py 2>&1 | tee -a /var/log/cron.log
        return $?
    fi
    return 1
}

# For cron jobs, wait before starting
if [ "$1" = "cron" ]; then
    sleep 30
fi

for i in $(seq 1 $MAX_RETRIES); do
    echo "Attempt $i of $MAX_RETRIES to start application"
    
    if run_app; then
        if [ "$1" != "cron" ]; then
            # For initial run, keep running in foreground
            tail -f /var/log/cron.log
        fi
        exit 0
    else
        echo "Setup failed, retrying in $RETRY_DELAY seconds..."
        sleep $RETRY_DELAY
    fi
done

echo "Failed to start after $MAX_RETRIES attempts"
exit 1
