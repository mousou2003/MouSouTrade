import logging
import boto3
import botocore
from botocore.exceptions import ClientError
import json
import os
import uuid
from datetime import datetime
from engine.VerticalSpread import VerticalSpread
from engine.data_model import DataModelBase, DirectionType, StrategyType

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
            if err.response['Error']['Code'] == 'ResourceNotFoundException':
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
                        {
                            'AttributeName': 'guid',
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

    def update_portfolio(self, portfolio: dict):
        """Update portfolio positions in database"""
        try:
            self.table.put_item(
                Item={
                    'type': 'portfolio',
                    'date': datetime.now().date().isoformat(),
                    'positions': portfolio
                }
            )
        except Exception as e:
            logger.error(f"Failed to update portfolio: {e}")

    def update_performance(self, performance: dict):
        """Store trade performance records"""
        try:
            self.table.put_item(
                Item={
                    'type': 'performance',
                    'date': datetime.now().date().isoformat(), 
                    'trades': performance
                }
            )
        except Exception as e:
            logger.error(f"Failed to update performance: {e}")

    def update_daily_performance(self, metrics: dict):
        """Store daily performance metrics"""
        try:
            self.table.put_item(
                Item={
                    'type': 'daily_performance',
                    'date': metrics['date'].isoformat(),
                    'metrics': metrics
                }
            )
        except Exception as e:
            logger.error(f"Failed to update daily performance: {e}")

    def query_spreads(self, ticker, update_date, expiration_date, 
                     direction: DirectionType = None, strategy: StrategyType = None,
                     guid: str = None):
        """Query spread opportunities with optional filters"""
        try:
            all_items = []
            if guid:
                # If GUID is provided, use it for direct lookup
                response = self.table.query(
                    IndexName='guid-index',
                    KeyConditionExpression='guid = :g',
                    ExpressionAttributeValues={':g': guid}
                )
                all_items = response.get('Items', [])
                logger.debug(f"GUID query returned {len(all_items)} items")
            else:
                if ticker is None or update_date is None or expiration_date is None:
                    logger.warning("Required parameters missing for querying spreads")
                    return []

                composite_key = self._create_composite_key(
                    ticker,
                    expiration_date,
                    update_date
                )

                # Build the query with KeyConditionExpression for both hash and range keys
                query_kwargs = {
                    'KeyConditionExpression': 'ticker = :t',
                    'ExpressionAttributeValues': {
                        ':t': composite_key
                    }
                }

                # If direction or strategy is specified, we need to search for matching option values
                if direction or strategy:
                    # Create the option JSON pattern to match
                    option_pattern = json.dumps({
                        "date": expiration_date.strftime(DataModelBase.DATE_FORMAT),
                        "direction": direction.value if direction else None,
                        "strategy": strategy.value if strategy else None
                    }, default=str)
                    
                    # Add begins_with condition for the option sort key
                    query_kwargs['KeyConditionExpression'] += ' AND begins_with(#opt, :opt_pattern)'
                    query_kwargs['ExpressionAttributeNames'] = {'#opt': 'option'}
                    query_kwargs['ExpressionAttributeValues'][':opt_pattern'] = option_pattern[:10]  # Use partial match

                response = self.table.query(**query_kwargs)
                all_items = response.get('Items', [])
                logger.debug(f"Query returned {len(all_items)} items")

            # Convert to spreads
            spreads = []
            for item in all_items:
                try:
                    spread = VerticalSpread().from_dict(item)
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

    def set_spreads(self, update_date: datetime, spread: VerticalSpread) -> tuple[bool, str]:
        """Store spread results in database
        Returns:
            tuple: (success: bool, guid: str) - Returns success status and GUID if successful
        """
        try:
            spread_guid = str(uuid.uuid4())
            
            key = {
                "ticker": self._create_composite_key(
                    spread.underlying_ticker, 
                    spread.expiration_date,
                    update_date
                ),
                "option": json.dumps({
                    "date": spread.expiration_date.strftime(DataModelBase.DATE_FORMAT), 
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

    def _create_composite_key(self, ticker: str, expiration_date: datetime, update_date: datetime) -> str:
        """Create a safe composite key with escaped special characters"""
        return f"{ticker};{expiration_date.strftime(DataModelBase.DATE_FORMAT)};{update_date.strftime(DataModelBase.DATE_FORMAT)}"

    def _parse_composite_key(self, composite_key: str) -> tuple:
        """Parse composite key back into components"""
        parts = composite_key.split(';')  # Changed from '##' to ';'
        if len(parts) == 3:
            return (parts[0], datetime.strptime(parts[1], DataModelBase.DATE_FORMAT).date(),
                   datetime.strptime(parts[2], DataModelBase.DATE_FORMAT).date())
        return None