FROM python:3.9-slim

WORKDIR /app

ENV PYTHONPATH="/app"

COPY ./app .
COPY ./engine engine
COPY ./marketdata_clients marketdata_clients
COPY ./database database
COPY ./config config
COPY ./app/crontab /etc/cron.d/app-cron
COPY ./.aws /root/.aws/

RUN apt-get update && apt-get install -y cron && \
    pip install --upgrade pip && \
    pip install -r requirements-run-app.txt && \
    pip install --upgrade boto3

# Give execution rights on the cron job
RUN chmod 0644 /etc/cron.d/app-cron

# Apply cron job
RUN crontab /etc/cron.d/app-cron

# Create the log file to be able to run tail
RUN touch /var/log/cron.log

# Run the script immediately and then start cron
CMD python /app/run.py && cron && tail -f /var/log/cron.log