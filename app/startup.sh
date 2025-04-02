#!/bin/bash
sleep 30
source /app/venv/bin/activate
python /app/run.py 1>> /var/log/cron.log 2>> /var/log/cron.error.log
