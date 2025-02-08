FROM python:3.9-slim

WORKDIR /app

COPY ./website/requirements-website.txt requirements.txt
COPY ./website/website.py .
COPY ./website/templates ./templates
COPY ./.aws /root/.aws/

RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install --upgrade boto3

CMD ["sh", "-c", "while true; do python website.py; sleep 10; done"]