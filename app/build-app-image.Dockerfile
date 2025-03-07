FROM python:3.8-slim

WORKDIR /app

COPY ./app . 
COPY ./engine engine 
COPY ./marketdata_clients marketdata_clients 
COPY ./database database 
COPY ./config config 
COPY ./app/crontab /etc/cron.d/app-cron 
COPY ./.aws /root/.aws/

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

# Update the package lists for APT
RUN apt-get update

# Install the required Python packages
RUN pip install -r requirements-run-app.txt

# Set the timezone
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Give execution rights on the cron job
RUN chmod 0644 /etc/cron.d/app-cron

# Apply the cron job
RUN crontab /etc/cron.d/app-cron

# Create the log file to be able to run tail
RUN touch /var/log/cron.log

# Run the script immediately and then start cron
CMD python /app/run.py && cron && tail -f /var/log/cron.log