FROM python:3.9-slim

WORKDIR /app

COPY ./run-engine/requirements-run-engine.txt requirements.txt
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install --upgrade boto3

COPY . .

CMD ["python", "run_engine.py", "./config/Fidelity.json"]