#!/bin/bash
# Set working directory
cd /app

log_date() {
    echo "[$(date)] Starting application..."
}

run_app() {
    log_date
    echo "Starting application setup..."
    # Load environment variables from /etc/environment
    set -a
    . /etc/environment
    set +a
    if [ $? -eq 0 ]; then
        printenv
        echo "Running application..."
        python /app/run.py
        return $?
    else
        echo "ERROR: Failed to load environment variables from /etc/environment."
        return 1
    fi
}

LOCKFILE="/tmp/myscript.lock"

if [ -e $LOCKFILE ]; then
    echo "Script is already running."
    exit 1
else
    touch $LOCKFILE
fi
trap 'rm -f $LOCKFILE' EXIT

if [ "$1" = "cron" ]; then
    echo "Running as a cron job..."
    # Redirect all output to both /var/log/cron.log and the terminal
    exec > >(tee -a /var/log/cron.log) 2>&1
else
    echo "Running initial startup..."
    exec > >(tee -a /var/log/app.log) 2>&1
fi

# Run the application
run_app
exit $?
