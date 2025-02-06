FROM python:3.9-slim

WORKDIR /app

ENV PYTHONPATH="/app"

COPY ./run_engine/requirements-run-engine.txt requirements.txt
RUN apt-get update && apt-get install -y cron && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install --upgrade boto3

COPY ./run_engine/run_engine.py /app/run_engine/run_engine.py
COPY ./PolygoneClients /app/PolygoneClients
COPY ./MarketDataClients /app/MarketDataClients
COPY ./engine /app/engine
COPY ./database /app/database
COPY ./config /app/config
COPY ./run_engine/crontab /etc/cron.d/run_engine-cron
COPY ./.aws /root/.aws/

# Give execution rights on the cron job
RUN chmod 0644 /etc/cron.d/run_engine-cron

# Apply cron job
RUN crontab /etc/cron.d/run_engine-cron

# Create the log file to be able to run tail
RUN touch /var/log/cron.log

# Run the script immediately and then start cron
CMD python /app/run_engine/run_engine.py ./config/Fidelity.json && cron && tail -f /var/log/cron.log