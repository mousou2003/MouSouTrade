from flask import Flask, render_template, jsonify
import boto3
from botocore.exceptions import ClientError
from decimal import Decimal
import json
import os
import signal
import sys

app = Flask(__name__)

# Configure DynamoDB connection
dynamodb_endpoint = os.getenv('DYNAMODB_ENDPOINT_URL', 'http://localhost:8000')
dynamodb = boto3.resource(
    'dynamodb',
    endpoint_url=dynamodb_endpoint,
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_DEFAULT_REGION')
)
table_name = 'Beta'
table = dynamodb.Table(table_name)

def convert_decimals(obj):
    """Helper function to convert Decimal types to float."""
    if isinstance(obj, Decimal):
        return float(obj)  # Convert Decimal to float
    elif isinstance(obj, list):
        return [convert_decimals(x) for x in obj]  # Recursively convert lists
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}  # Recursively convert dicts
    return obj  # Return the object if it's not Decimal, list, or dict

def get_all_items():
    print("Fetching all items from the DynamoDB table.")
    try:
        response = table.scan()
        return response['Items']
    except ClientError as e:
        print(f"Unable to scan the DynamoDB table: {e.response['Error']['Message']}")
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    records = get_all_items()
    try:
        # Convert Decimal types to float for JSON serialization
        records = convert_decimals(records)
        return jsonify(records)
    except Exception as e:
        print(f"Error converting records: {e}")
        return jsonify([])

def signal_handler(sig, frame):
    print('Gracefully shutting down...')
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_handler)
    app.run(host='0.0.0.0', port=5000)