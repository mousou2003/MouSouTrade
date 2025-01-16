FROM python:3.9-slim

WORKDIR /app

COPY ./website/requirements-website.txt requirements.txt
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install --upgrade boto3

COPY . .
CMD ["python", "website.py"]