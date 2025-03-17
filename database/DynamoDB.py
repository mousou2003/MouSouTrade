import logging
import boto3
import botocore
from botocore.exceptions import ClientError
import json
import os
import uuid
from datetime import datetime
from engine.data_model import DirectionType, SpreadDataModel, StrategyType

logger = logging.getLogger(__name__)

class DynamoDB:
    def __init__(self, table_name):
        logger.debug("Init Database")
        # Check for required environment variables
        required_env_vars = ['DYNAMODB_ENDPOINT_URL']
        missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]

        if missing_env_vars:
            raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_env_vars)}")

        endpoint_url = os.getenv('DYNAMODB_ENDPOINT_URL', 'http://localhost:8000')
        dynamodb = boto3.Session().resource('dynamodb', endpoint_url=endpoint_url)
        logger.debug("Dynamo client created at endpoint %s" % endpoint_url)

        try:
            self.table = dynamodb.Table(table_name)
            self.table.load()
            logger.debug("Table exists %s" % table_name)
        except ClientError as err:
            if (err.response['Error']['Code'] == 'ResourceNotFoundException'):
                logger.debug("Create the DynamoDB table.")
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
                        }
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
                        {
                            'AttributeName': 'guid',
                            'AttributeType': 'S'
                        },
                        {
                            'AttributeName': 'type',
                            'AttributeType': 'S'
                        },
                        {
                            'AttributeName': 'date',
                            'AttributeType': 'S'
                        }
                    ],
                    GlobalSecondaryIndexes=[
                        {
                            'IndexName': 'guid-index',
                            'KeySchema': [
                                {
                                    'AttributeName': 'guid',
                                    'KeyType': 'HASH'
                                }
                            ],
                            'Projection': {
                                'ProjectionType': 'ALL'
                            },
                            'ProvisionedThroughput': {
                                'ReadCapacityUnits': 5,
                                'WriteCapacityUnits': 5
                            }
                        },
                        {
                            'IndexName': 'type-date-index',
                            'KeySchema': [
                                {
                                    'AttributeName': 'type',
                                    'KeyType': 'HASH'
                                },
                                {
                                    'AttributeName': 'date',
                                    'KeyType': 'RANGE'
                                }
                            ],
                            'Projection': {
                                'ProjectionType': 'ALL'
                            },
                            'ProvisionedThroughput': {
                                'ReadCapacityUnits': 5,
                                'WriteCapacityUnits': 5
                            }
                        }
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

    def get_item(self, key):
        try:
            return self.table.get_item(Key=key)
        except botocore.exceptions.EndpointConnectionError as err:
            logger.error(
                "Couldn't access endpoint %s. Here's why: %s",
                self.table,
                err)
            raise

    def put_item(self, item):
        try:
            return self.table.put_item(Item=item)
        except botocore.exceptions.EndpointConnectionError as err:
            logger.error(
                "Couldn't access endpoint %s. Here's why: %s",
                self.table,
                err)
            raise

    # Add constants for record types at class level
    RECORD_TYPE_SPREAD = "SPREAD"
    RECORD_TYPE_PERFORMANCE = "PERFORMANCE"
    RECORD_TYPE_PORTFOLIO = "PORTFOLIO"

    def update_portfolio(self, portfolio: dict, spread_guid: str):
        """Update portfolio positions in database with spread reference"""
        try:
            date = datetime.now().date().isoformat()
            self.table.put_item(
                Item={
                    'ticker': f"{self.RECORD_TYPE_PORTFOLIO}",
                    'option': f"positions_{date}",
                    'spread_guid': spread_guid,  # Reference to spread
                    'type': 'portfolio',
                    'date': date,
                    'positions': portfolio
                }
            )
        except Exception as e:
            logger.error(f"Failed to update portfolio: {e}")

    def update_performance(self, performance: dict, spread_guid: str):
        """Store trade performance records with spread reference"""
        try:
            date = datetime.now().date().isoformat()
            self.table.put_item(
                Item={
                    'ticker': f"{self.RECORD_TYPE_PERFORMANCE}",
                    'option': f"trades_{date}",
                    'spread_guid': spread_guid,  # Reference to spread
                    'type': 'performance',
                    'date': date,
                    'trades': performance
                }
            )
        except Exception as e:
            logger.error(f"Failed to update performance: {e}")

    def update_daily_performance(self, metrics: dict):
        """Store daily performance metrics"""
        try:
            performance_date = metrics['date']
            self.table.put_item(
                Item={
                    'ticker': f"PERFORMANCE;{performance_date}",  # Primary key
                    'option': 'daily_metrics',  # Sort key
                    'type': 'daily_performance',
                    'date': performance_date,
                    'metrics': metrics
                }
            )
        except Exception as e:
            logger.error(f"Failed to update daily performance: {e}")

    def query_spreads(self, ticker, expiration_date, 
                     direction: DirectionType = None, strategy: StrategyType = None,
                     guid: str = None):
        """Query spread opportunities with optional filters"""
        try:
            all_items = []
            if guid:  # Remove unnecessary parentheses
                # If GUID is provided, use it for direct lookup
                response = self.table.query(
                    IndexName='guid-index',
                    KeyConditionExpression='guid = :g',
                    ExpressionAttributeValues={':g': guid}
                )
                all_items = response.get('Items', [])
                logger.debug(f"GUID query returned {len(all_items)} items")
            else:
                if ticker is None or expiration_date is None:
                    logger.warning("Required parameters missing for querying spreads")
                    return []

                # Use ticker directly instead of composite key
                query_kwargs = {
                    'KeyConditionExpression': 'ticker = :t',
                    'ExpressionAttributeValues': {
                        ':t': ticker  # Use ticker directly
                    }
                }

                # If direction or strategy is specified, add to option pattern
                if direction or strategy:
                    option_pattern = json.dumps({
                        "direction": direction.value if direction else None,
                        "strategy": strategy.value if strategy else None
                    }, default=str)
                    
                    query_kwargs['KeyConditionExpression'] += ' AND begins_with(#opt, :opt_pattern)'
                    query_kwargs['ExpressionAttributeNames'] = {'#opt': 'option'}
                    query_kwargs['ExpressionAttributeValues'][':opt_pattern'] = option_pattern[:10]

                response = self.table.query(**query_kwargs)
                all_items = response.get('Items', [])
                logger.debug(f"Query returned {len(all_items)} items")

            # Convert to spreads
            spreads = []
            for item in all_items:
                try:
                    spread = SpreadDataModel.from_dict(item)
                    spread.spread_guid = item.get('guid')  # Set the guid from the database item
                    spreads.append(spread)
                except Exception as e:
                    logger.warning(f"Failed to parse spread: {e}")
                    continue
            
            logger.debug(f"Returning {len(spreads)} matched spreads")
            return spreads

        except Exception as e:
            logger.error(f"Failed to query spreads: {e}")
            logger.exception(e)
            return []

    def set_spreads(self, spread: SpreadDataModel) -> tuple[bool, str]:
        """Store spread results in database
        Returns:
            tuple: (success: bool, guid: str) - Returns success status and GUID if successful
        """
        try:
            spread_guid = str(uuid.uuid4())
            
            key = {
                "ticker": f"{self.RECORD_TYPE_SPREAD};{spread.first_leg_contract.ticker}",
                "option": json.dumps({
                    "direction": spread.direction.value, 
                    "strategy": spread.strategy.value
                }, default=str),
                "guid": spread_guid
            }

            merged_json = {**key, **{"description": spread.get_description()}, **spread.to_dict()}
            
            response = self.put_item(item=merged_json)
            success = response.get('ResponseMetadata')['HTTPStatusCode'] == 200
            return success, spread_guid if success else ""

        except Exception as e:
            logger.error(f"Failed to set spreads: {e}")
            return False, ""

    def verify_spread(self, guid: str) -> bool:
        """Verify a spread was saved correctly by checking its GUID
        Args:
            guid: The GUID of the spread to verify
        Returns:
            bool: True if spread exists and is valid
        """
        try:
            spreads = self.query_spreads(None, None, None, guid=guid)
            return len(spreads) == 1
        except Exception as e:
            logger.error(f"Failed to verify spread: {e}")
            return False

    def flush_table(self):
        """Delete all items from the table"""
        try:
            scan = self.table.scan()
            with self.table.batch_writer() as batch:
                for item in scan['Items']:
                    batch.delete_item(
                        Key={
                            'ticker': item['ticker'],
                            'option': item['option']
                        }
                    )
            logger.info("Table flushed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to flush table: {e}")
            return False

    def count_items(self) -> int:
        """Count total items in table"""
        try:
            response = self.table.scan(Select='COUNT')
            return response['Count']
        except Exception as e:
            logger.error(f"Failed to count items: {e}")
            return -1

    def scan_spreads(self)-> list[SpreadDataModel]:
        """Scan all spread records from the table"""
        logger.info("Scanning all spread records")
        try:
            items = []
            paginator = self.table.meta.client.get_paginator('scan')
            
            # Filter for spread records only
            for page in paginator.paginate(
                TableName=self.table.name,
                FilterExpression='begins_with(ticker, :prefix)',
                ExpressionAttributeValues={':prefix': self.RECORD_TYPE_SPREAD}
            ):
                items.extend(page['Items'])
            return [SpreadDataModel.from_dict(record) for record in items]
        except ClientError as e:
            logger.error(f"Unable to scan the DynamoDB table: {e.response['Error']['Message']}")
            raise
        except Exception as e:
            logger.error(f"Error scanning table: {e}")
            raise

    def query_by_spread_guid(self, spread_guid: str) -> dict:
        """Query all records related to a specific spread by its GUID"""
        try:
            # First get the spread using GUID index
            spreads = self.query_spreads(None, None, guid=spread_guid)
            if not spreads:
                return {}

            # Then get related records by filtering on spread_guid
            response = self.table.scan(
                FilterExpression='spread_guid = :guid',
                ExpressionAttributeValues={':guid': spread_guid}
            )
            items = response.get('Items', [])
            
            result = {
                'spread': spreads[0],
                'performance': [],
                'portfolio': []
            }
            
            for item in items:
                if item['type'] == 'performance':
                    result['performance'].append(item)
                elif item['type'] == 'portfolio':
                    result['portfolio'].append(item)
                
            return result
        except Exception as e:
            logger.error(f"Failed to query by spread GUID: {e}")
            return {}