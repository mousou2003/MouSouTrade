#!/bin/bash

log_date() {
    echo "[$(date)] Starting application..." | tee -a /var/log/cron.log
}

run_app() {
    log_date
    echo "Starting application setup..." | tee -a /var/log/cron.log
    if source /app/setup_env.sh; then
        echo "Running application..." | tee -a /var/log/cron.log
        python /app/run.py 2>&1 | tee -a /var/log/cron.log
        return $?
    else
        echo "ERROR: Failed to source environment setup script." | tee -a /var/log/cron.log
        return 1
    fi
}

if [ "$1" = "cron" ]; then
    echo "Running as a cron job..." | tee -a /var/log/cron.log
else
    echo "Running initial startup..." | tee -a /var/log/cron.log
fi

# Run the application
run_app
exit $?
