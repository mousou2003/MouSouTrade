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
ARG PYTHONPATH
ARG WEBSITE_PORT
ARG DYNAMODB_PORT
ARG PROJECT_NAME
ARG MOUSOUTRADE_CLIENTS

# Set environment variables
ENV AWS_PROFILE=$AWS_PROFILE
ENV AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID
ENV AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
ENV AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION
ENV DYNAMODB_ENDPOINT_URL=$DYNAMODB_ENDPOINT_URL
ENV MOUSOUTRADE_CONFIG_FILE=$MOUSOUTRADE_CONFIG_FILE
ENV MOUSOUTRADE_STAGE=$MOUSOUTRADE_STAGE
ENV MOUSOUTRADE_VERSION=$MOUSOUTRADE_VERSION
ENV PYTHONPATH=$PYTHONPATH
ENV WEBSITE_PORT=$WEBSITE_PORT
ENV DYNAMODB_PORT=$DYNAMODB_PORT
ENV PROJECT_NAME=$PROJECT_NAME
ENV TZ="America/Los_Angeles"
ENV MOUSOUTRADE_CLIENTS=$MOUSOUTRADE_CLIENTS

# System setup and create non-root user
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
    echo $TZ > /etc/timezone && \
    useradd -m -r appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user for pip
USER appuser

# Application setup with pip
RUN python -m venv /app/venv && \
    . /app/venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-run-app.txt

# Switch back to root for cron operations
USER root

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

# Set PATH to include venv
ENV PATH="/app/venv/bin:$PATH"

# Run the script immediately and then start cron
CMD python /app/run.py && cron && tail -f /var/log/cron.log