import logging

import boto3
import botocore
import boto3.dynamodb
from botocore.exceptions import ClientError

import json
import os
# test with command lines  aws dynamodb list-tables --profile 851655311094_AdministratorAccess --endpoint-url 'localhost:8000'
logger = logging.getLogger(__name__)
class Database():
    def __init__(self,table_name):
        logger.info("Init Database")
        
        # Check for required environment variables
        required_env_vars = ['DYNAMODB_ENDPOINT_URL']
        missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]

        if missing_env_vars:
            raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_env_vars)}")

        endpoint_url = os.getenv('DYNAMODB_ENDPOINT_URL', 'http://localhost:8000')
        dynamodb = boto3.Session().resource('dynamodb', endpoint_url=endpoint_url)
        logger.info("dynamo client created at endpoint %s" % endpoint_url)

        try:
            self.table = dynamodb.Table(table_name)
            self.table.load()
            logger.info("table exist %s" % table_name)
        except ClientError as err:
            if err.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.info("Create the DynamoDB table.")
                self.table = dynamodb.create_table(
                    TableName=table_name,
                    KeySchema=[
                        {
                            'AttributeName': 'ticker',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'option',
                            'KeyType': 'RANGE'
                        },
                    ],
                    AttributeDefinitions=[
                        {
                            'AttributeName': 'ticker',
                            'AttributeType': 'S'
                        },
                        {
                            'AttributeName': 'option',
                            'AttributeType': 'S'
                        },
                    ],
                    ProvisionedThroughput={
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                )

                logger.info("Wait until the table exists.")
                self.table.wait_until_exists()
            else:
                logger.warning(
                    "Couldn't check for existence of %s. Here's why: %s: %s",
                    table_name,
                    err.response['Error']['Code'], err.response['Error']['Message'])
                raise err

    def get_item(self, Key):
        try:
            return self.table.get_item(Key=Key)
        except botocore.exceptions.EndpointConnectionError as err:
            logger.error(
                "Couldn't access endpoint %s. Here's why: %s",
                self.table,
                err)

    def put_item(self, Item):
        try:
            return self.table.put_item( Item = Item)
        except botocore.exceptions.EndpointConnectionError as err:
            logger.error(
                "Couldn't access endpoint %s. Here's why: %s",
                self.table,
                err)