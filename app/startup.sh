#!/bin/bash

MAX_RETRIES=3
RETRY_DELAY=5

log_date() {
    echo "[$(date)] Starting application..." >> /var/log/cron.log
}

run_app() {
    log_date
    echo "Starting application setup..."
    if source /app/setup_env.sh; then
        echo "Running application..."
        python /app/run.py 2>&1 | tee -a /var/log/cron.log
        return $?
    else
        echo "ERROR: Failed to source environment setup script."
        return 1
    fi
}

if [ "$1" = "cron" ]; then
    echo "Running as a cron job..."
else
    echo "Running initial startup..."
    for i in $(seq 1 $MAX_RETRIES); do
        echo "Attempt $i of $MAX_RETRIES to start application"
        if run_app; then
            echo "Application started successfully."
            tail -f /var/log/cron.log
            exit 0
        else
            echo "Setup failed, retrying in $RETRY_DELAY seconds..."
            sleep $RETRY_DELAY
        fi
    done
    echo "ERROR: Failed to start application after $MAX_RETRIES attempts."
    exit 1
fi

# For cron jobs, run the application once
run_app
