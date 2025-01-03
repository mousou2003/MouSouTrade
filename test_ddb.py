from colorama import Fore
import json
import sys
from requests import ReadTimeout
import logging

import boto3
import botocore
import boto3.dynamodb
from botocore.exceptions import ClientError

from PolygoneClients.PolygoneClient import PolygoneClient
from engine.Options import CreditSpread, Option
from MarketDataClients.MarketDataClient import MarketDataException
import engine.data_model as dm

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)

# test with command lines  aws dynamodb list-tables --profile 851655311094_AdministratorAccess --endpoint-url 'localhost:8000'
table_name = 'test450'
try:
    # Get the service resource.
    dynamodb = boto3.Session(profile_name='851655311094_AdministratorAccess').resource(
        'dynamodb', endpoint_url='http://localhost:8000')
    logger.info("dynamo client created")

    try:
        table = dynamodb.Table(table_name)
        table.load()
        logger.info("table exist %s" % table)
    except ClientError as err:
        if err.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.info("Create the DynamoDB table.")
            table = dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {
                        'AttributeName': 'username',
                        'KeyType': 'HASH'
                    },
                    {
                        'AttributeName': 'last_name',
                        'KeyType': 'RANGE'
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'username',
                        'AttributeType': 'S'
                    },
                    {
                        'AttributeName': 'last_name',
                        'AttributeType': 'S'
                    },
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )

            logger.info("Wait until the table exists.")
            table.wait_until_exists()
        else:
            logger.error(
                "Couldn't check for existence of %s. Here's why: %s: %s",
                table_name,
                err.response['Error']['Code'], err.response['Error']['Message'])
            raise

    logger.info("put an item")
    with open(sys.argv[1]) as file:
        stocks = json.load(file)
        for stock in stocks:
            try:
                direction = dm.BULLISH
                strategy = dm.CREDIT
                creditVerticalSpreadTest = CreditSpread(
                    underlying_ticker=stock['Ticker'], direction=direction, strategy=strategy, client=PolygoneClient())
                if creditVerticalSpreadTest.matchOption(date=Option.get_followingThirdFriday()):
                    print(
                        Fore.GREEN + creditVerticalSpreadTest.get_plain_English_Result()+Fore.RESET)
                else:
                    logger.info("No match for %s" % stock['Ticker'])
                logger.info(creditVerticalSpreadTest.toJSON())
                table.put_item(
                    Item=creditVerticalSpreadTest.toJSON()
                    )
            except MarketDataException as e:
                logger.warning("Fail to get options %s" % stock['Ticker'])
                logger.warning(e)
            except ReadTimeout as e:
                logger.warning("Readtimeout for %s" % stock['Ticker'])
                logger.warning(e)
                PolygoneClient().release()

    logger.info("get an item")
    response = table.get_item(
        Key={
            'username': 'janedoe',
            'last_name': 'Doe'
        }
    )
    # item = response['Item']
    logger.info("response: %s" % response)
except botocore.exceptions.EndpointConnectionError as err:
    logger.error(
        "Couldn't access endpoint %s. Here's why: %s",
        table_name,
        err)
except Exception as err:
    logger.error(
        "Couldn't access endpoint %s. Here's why: %s",
        table_name,
        err)
