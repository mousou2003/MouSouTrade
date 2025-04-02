FROM python:3.12.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY ./app/requirements-run-app.txt .

# Infrequently changed files
COPY ./app/crontab /etc/cron.d/app-cron 
COPY ./.aws /root/.aws/
COPY ./config config 

# Define build arguments
ARG APP_CODE_PATHS="engine marketdata_clients database agents"
ARG AWS_PROFILE
ARG AWS_ACCESS_KEY_ID
ARG AWS_SECRET_ACCESS_KEY
ARG AWS_DEFAULT_REGION
ARG DYNAMODB_ENDPOINT_URL
ARG MOUSOUTRADE_CONFIG_FILE
ARG MOUSOUTRADE_STAGE
ARG MOUSOUTRADE_VERSION
ARG WEBSITE_PORT
ARG DYNAMODB_PORT
ARG PROJECT_NAME
ARG MOUSOUTRADE_CLIENTS
ENV TZ="America/Los_Angeles"

# Set environment variables
ENV AWS_PROFILE=$AWS_PROFILE
ENV APP_CODE_PATHS=$APP_CODE_PATHS
ENV AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID
ENV AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
ENV AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION
ENV DYNAMODB_ENDPOINT_URL=$DYNAMODB_ENDPOINT_URL
ENV MOUSOUTRADE_CONFIG_FILE=$MOUSOUTRADE_CONFIG_FILE
ENV MOUSOUTRADE_STAGE=$MOUSOUTRADE_STAGE
ENV MOUSOUTRADE_VERSION=$MOUSOUTRADE_VERSION
ENV WEBSITE_PORT=$WEBSITE_PORT
ENV DYNAMODB_PORT=$DYNAMODB_PORT
ENV PROJECT_NAME=$PROJECT_NAME
ENV TZ="America/Los_Angeles"
ENV MOUSOUTRADE_CLIENTS=$MOUSOUTRADE_CLIENTS

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
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-run-app.txt
COPY ./app .

# Copy and setup scripts
COPY ./app/setup_env.sh /app/
COPY ./app/startup.sh /app/
RUN chmod +x /app/setup_env.sh && \
    chmod +x /app/startup.sh

# Cron setup
RUN chmod 0644 /etc/cron.d/app-cron && \
    crontab /etc/cron.d/app-cron && \
    touch /var/log/cron.log

# Copy code from staging
COPY ./build/staging/. /app/


# Verify directories
RUN echo "Verifying code directories:" && \
    for path in ${APP_CODE_PATHS}; do \
        if [ ! -d "/app/$path" ]; then \
            echo "ERROR: Directory /app/$path not found" && exit 1; \
        else \
            echo "Found directory /app/$path:" && \
            ls -la "/app/$path"; \
        fi \
    done

# Run cron and startup script
CMD ["/bin/bash", "-c", "cron && /app/startup.sh"]