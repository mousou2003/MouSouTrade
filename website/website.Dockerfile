FROM python:3.12.9-slim AS builder

WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY ./website/requirements-website.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade boto3

FROM python:3.12.9-slim

WORKDIR /app

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

# Install only necessary packages and clean up in one layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends cron iputils-ping && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/

# Copy application files
COPY ./website/website.py .
COPY ./website/templates ./templates
COPY ./.aws /root/.aws/
COPY ./engine ./engine
COPY ./marketdata_clients ./marketdata_clients
COPY ./database ./database

# Use exec form of CMD for better signal handling
CMD ["sh", "-c", "while true; do python website.py; sleep 10; done"]