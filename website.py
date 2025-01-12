from flask import Flask, render_template, jsonify
import boto3
from botocore.exceptions import ClientError
from decimal import Decimal
import json

app = Flask(__name__)

# Configure DynamoDB connection
dynamodb = boto3.resource('dynamodb')
table_name = 'Beta'  # Replace this with your DynamoDB table name
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
        converted_records = convert_decimals(records)
        return jsonify(converted_records)  # Return the records as JSON
    except Exception as e:
        # Handle JSON conversion and other exceptions
        print(f"JSON Exception: {str(e)}")
        return jsonify({"error": "Failed to serialize data to JSON."}), 500

if __name__ == '__main__':
    app.run(debug=True)