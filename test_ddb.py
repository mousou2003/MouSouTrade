import json.tool
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
from MarketDataClients.MarketDataClient import *
import engine.data_model as dm
import datetime

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)

# test with command lines  aws dynamodb list-tables --profile 851655311094_AdministratorAccess --endpoint-url 'localhost:8000'
table_name = 'test800'
try:
    # Get the service resource.
    dynamodb = boto3.Session().resource(
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
                        'AttributeName': 'ticker',
                        'KeyType': 'HASH'
                    },
                    {
                        'AttributeName': 'date',
                        'KeyType': 'RANGE'
                    },
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'ticker',
                        'AttributeType': 'S'
                    },
                    {
                        'AttributeName': 'date',
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
            logger.warning(
                "Couldn't check for existence of %s. Here's why: %s: %s",
                table_name,
                err.response['Error']['Code'], err.response['Error']['Message'])
            exit

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
                #logger.info(creditVerticalSpreadTest.toJSON())
                Key={
                    "date": datetime.date.today().isoformat(),
                    "ticker": stock['Ticker']
                }

                # Check for item existence in the response
                if 'Item' in table.get_item(Key=Key):
                   logger.info("info already stored for %s" % Key)
                else:
                    merged_json = {**Key,**{"info":creditVerticalSpreadTest.toJSON()}}
                    table.put_item( Item= merged_json)
                    response = table.get_item(Key=Key)
                    if 'Item' in response:
                        logger.info("info  stored for %s" % Key)
                        logger.debug("saved in table: %s" % response)
                    else:
                        raise MarketDataStorageFailedException()
                        
            except MarketDataStorageFailedException as e:
                logger.warning("Fail to get item from storage %s" % Key)
                logger.warning(e)
            except MarketDataException as e:
                logger.warning("Fail to get options %s" % Key)
                logger.warning(e)
            except ReadTimeout as e:
                logger.warning("Readtimeout for %s" % Key)
                logger.warning(e)
                PolygoneClient().release()


except botocore.exceptions.EndpointConnectionError as err:
    logger.error(
        "Couldn't access endpoint %s. Here's why: %s",
        table_name,
        err)
    PolygoneClient().release()
except Exception as err:
    logger.error(
        "Unknow issue with %s. Here's why: %s",
        table_name,
        err)
    PolygoneClient().release()
