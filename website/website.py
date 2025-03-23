from flask import Flask, render_template, jsonify
from database.DynamoDB import DynamoDB
import os
import signal
import sys
import logging
from engine.data_model import SpreadDataModel

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Check for required environment variables
required_env_vars = ['DYNAMODB_ENDPOINT_URL', 'MOUSOUTRADE_STAGE', 'WEBSITE_PORT']
missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_env_vars:
    logging.error(f"Error: Missing required environment variables: {', '.join(missing_env_vars)}")
    sys.exit(1)

db = DynamoDB(os.getenv('MOUSOUTRADE_STAGE'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    try:
        # Ensure data structure matches SpreadDataModel and provide default values
        validated_records: list[dict] = [record.to_dict() for record in db.scan_spreads()]
        return jsonify(validated_records)
    except Exception as e:
        logging.error(f"{e}")
        return jsonify({"error": "An error occurred while fetching data. Please try again later."}), 500

def signal_handler(sig, frame):
    logging.info('Gracefully shutting down...')
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_handler)
    website_port = int(os.getenv('WEBSITE_PORT'))
    logging.info(f"Website is running at http://localhost:{website_port}")
    app.run(host='0.0.0.0', port=website_port)
