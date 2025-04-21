#!/bin/bash

# Redirect all output to /var/log/cron.log
exec >> /var/log/cron.log 2>&1

log_date() {
    echo "[$(date)] Starting application..."
}

run_app() {
    log_date
    echo "Starting application setup..."
    if source /app/setup_env.sh; then
        echo "Running application..."
        python /app/run.py
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
fi

# Run the application
run_app
exit $?
