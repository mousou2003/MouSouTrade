FROM python:3.9-slim

WORKDIR /app

COPY ./run-engine/requirements-run-engine.txt requirements.txt
RUN apt-get update && apt-get install -y cron && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install --upgrade boto3

COPY ./run_engine.py /app/run_engine.py
COPY ./PolygoneClients /app/PolygoneClients
COPY ./MarketDataClients /app/MarketDataClients
COPY ./engine /app/engine
COPY ./database /app/database
COPY ./config /app/config
COPY ./run-engine/crontab /etc/cron.d/run-engine-cron
COPY ./.aws /root/.aws/

# Give execution rights on the cron job
RUN chmod 0644 /etc/cron.d/run-engine-cron

# Apply cron job
RUN crontab /etc/cron.d/run-engine-cron

# Create the log file to be able to run tail
RUN touch /var/log/cron.log

# Run the script immediately and then start cron
CMD python run_engine.py ./config/Fidelity.json && cron && tail -f /var/log/cron.log