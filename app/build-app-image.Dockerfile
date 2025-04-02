FROM python:3.12.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY ./app/requirements-run-app.txt .

# Infrequently changed files
COPY ./app/crontab /etc/cron.d/app-cron 
COPY ./.aws /root/.aws/
COPY ./config config 

# Define build arguments
ARG AWS_PROFILE
ARG AWS_ACCESS_KEY_ID
ARG AWS_SECRET_ACCESS_KEY
ARG AWS_DEFAULT_REGION
ARG DYNAMODB_ENDPOINT_URL
ARG MOUSOUTRADE_CONFIG_FILE
ARG MOUSOUTRADE_STAGE
ARG MOUSOUTRADE_VERSION
ENV PYTHONPATH=/app:/app/engine:/app/marketdata_clients:/app/database:/app/agents
ARG WEBSITE_PORT
ARG DYNAMODB_PORT
ARG PROJECT_NAME
ARG MOUSOUTRADE_CLIENTS
ENV TZ="America/Los_Angeles"

# System setup
RUN apt-get update && \
    apt-get install -y \
    python3 \
    python3-pip \
    cron \
    iputils-ping \
    vim \
    net-tools && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone

# Application setup with pip
COPY ./app/setup_venv_env.sh /app/
RUN chmod +x /app/setup_venv_env.sh && \
    mkdir -p /app/venv && \
    chmod 755 /app/venv && \
    python -m venv /app/venv && \
    chmod -R 755 /app/venv && \
    . /app/venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-run-app.txt && \
    /app/setup_venv_env.sh

# Cron setup
RUN chmod 0644 /etc/cron.d/app-cron && \
    crontab /etc/cron.d/app-cron && \
    touch /var/log/cron.log

# Frequently changed application code
COPY ./app . 
COPY ./engine engine 
COPY ./marketdata_clients marketdata_clients 
COPY ./database database 
COPY ./agents agents

# Run cron in foreground
CMD cron && tail -f /var/log/cron.log