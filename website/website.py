from flask import Flask, render_template, jsonify
import boto3
from botocore.exceptions import ClientError
import os
import signal
import sys
import logging
from engine.data_model import DataModelBase, SpreadDataModel, Contract  # Correct the import statement

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Check for required environment variables
required_env_vars = [
    'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION', 
    'DYNAMODB_ENDPOINT_URL', 'MOUSOUTRADE_STAGE', 'WEBSITE_PORT'
]
missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_env_vars:
    logging.error(f"Error: Missing required environment variables: {', '.join(missing_env_vars)}")
    sys.exit(1)

# Print the values of the environment variables
for var in required_env_vars:
    logging.info(f"{var}: {os.getenv(var)}")

# Configure DynamoDB connection
dynamodb_endpoint = os.getenv('DYNAMODB_ENDPOINT_URL')
dynamodb = boto3.resource(
    'dynamodb',
    endpoint_url=dynamodb_endpoint,
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_DEFAULT_REGION')
)
table_name = os.getenv('MOUSOUTRADE_STAGE')
table = dynamodb.Table(table_name)

def get_all_items():
    logging.info("Fetching all items from the DynamoDB table.")
    try:
        response = table.scan()
        items = response['Items']
        for item in items:
            try:
                ticker, target_expiration_date, update_date = item['ticker'].split(';')
                item['underlying_ticker'] = ticker
                item['expiration_date'] = target_expiration_date
                item['update_date'] = update_date
            except ValueError:
                logging.warning(f"Warning: Skipping record with old format: {item['ticker']}")
                continue
        return items
    except ClientError as e:
        logging.error(f"Unable to scan the DynamoDB table: {e.response['Error']['Message']}")
        return []
    except ConnectionRefusedError as e:
        logging.error(f"Connection refused: {e}")
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    records = get_all_items()
    try:
        # Ensure data structure matches SpreadDataModel and provide default values
        validated_records = [SpreadDataModel.from_dynamodb(record).to_dict() for record in records]
        return jsonify(validated_records)
    except Exception as e:
        logging.error(f"Error converting records: {e}")
        return jsonify([])

def signal_handler(sig, frame):
    logging.info('Gracefully shutting down...')
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_handler)
    website_port = int(os.getenv('WEBSITE_PORT'))
    logging.info(f"Website is running at http://localhost:{website_port}")
    app.run(host='0.0.0.0', port=website_port)
