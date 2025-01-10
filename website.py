from flask import Flask, render_template
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__)

# Configure DynamoDB connection
dynamodb = boto3.resource('dynamodb')
table_name = 'Beta'  # Replace this with your DynamoDB table name
table = dynamodb.Table(table_name)

def get_all_items():
    print("Fetch all items from the DynamoDB table.")
    try:
        response = table.scan()  # Scan the entire table (can be costly for large tables)
        return response['Items']
    except ClientError as e:
        print("Unable to scan the DynamoDB table:")
        print(e.response['Error']['Message'])
        return []

@app.route('/')
def index():
    """Home page to display database content."""
    records = get_all_items()  # Fetch records
    print(records)
    return render_template('index.html', records=records)

if __name__ == '__main__':
    app.run(debug=True)