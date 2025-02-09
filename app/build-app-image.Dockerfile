FROM python:3.9-slim

WORKDIR /app

ENV PYTHONPATH="/app"

COPY ./app/requirements-run-app.txt requirements.txt
COPY ./app/app.py /app/app/app.py
COPY ./PolygoneClients /app/PolygoneClients
COPY ./MarketDataClients /app/MarketDataClients
COPY ./app /app/app
COPY ./database /app/database
COPY ./config /app/config
COPY ./app/crontab /etc/cron.d/app-cron
COPY ./.aws /root/.aws/

RUN apt-get update && apt-get install -y cron && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install --upgrade boto3

# Give execution rights on the cron job
RUN chmod 0644 /etc/cron.d/app-cron

# Apply cron job
RUN crontab /etc/cron.d/app-cron

# Create the log file to be able to run tail
RUN touch /var/log/cron.log

# Run the script immediately and then start cron
CMD python /app/app/app.py && cron && tail -f /var/log/cron.log