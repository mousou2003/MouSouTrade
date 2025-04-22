FROM python:3.12.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY ./app/requirements-run-app.txt .

# Infrequently changed files
COPY ./app/crontab /etc/cron.d/app-cron 
COPY ./.aws /root/.aws/
COPY ./config config 

# Copy the .env file into the container
COPY .env /app/.env

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
    ln -snf /usr/share/zoneinfo/America/Los_Angeles /etc/localtime && \
    echo "America/Los_Angeles" > /etc/timezone

# Application setup with pip
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-run-app.txt

# Copy and setup scripts
COPY ./app/setup_env.sh /app/
COPY ./app/startup.sh /app/
RUN chmod +x /app/setup_env.sh && \
    chmod +x /app/startup.sh

# Cron setup
COPY ./app/crontab /etc/cron.d/app-cron
RUN chmod 0644 /etc/cron.d/app-cron && \
    crontab /etc/cron.d/app-cron && \
    touch /var/log/cron.log

# Copy code from staging
COPY ./build/staging/. /app/

# Validate environment and directories
RUN /app/setup_env.sh

# Run cron in the foreground
CMD ["cron", "-f"]