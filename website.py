from flask import Flask, render_template, jsonify
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__)

# Configure DynamoDB connection
dynamodb = boto3.resource('dynamodb')
table_name = 'Beta'  # Replace this with your DynamoDB table name
table = dynamodb.Table(table_name)

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
    print(records)
    return jsonify(records)

if __name__ == '__main__':
    app.run(debug=True)