import json.tool
import traceback
from colorama import Fore
import json
import sys
from requests import ReadTimeout
import logging

from PolygoneClients.PolygoneClient import PolygoneClient
from engine.Options import CreditSpread, Option
from MarketDataClients.MarketDataClient import *
import engine.data_model as dm
import datetime
from database.src import Database

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)

try:
    db = Database.Database("Beta")
    with open(sys.argv[1]) as file:
        stocks = json.load(file)
        for stock in stocks:
            try:
                direction = dm.BULLISH
                strategy = dm.CREDIT
                Key={
                    "ticker": stock['Ticker'],
                    "option": json.dumps({"date":datetime.date.today(), "direction":direction, "strategy":strategy}, default=str)
                }
                merged_json = Key

                # Check for item existence in the response
                if 'Item' in db.get_item(Key=Key):
                   logger.info("info already stored for %s" % Key)
                else:
                    creditVerticalSpreadTest = CreditSpread(
                        underlying_ticker=stock['Ticker'], direction=direction, strategy=strategy, client=PolygoneClient())
                    
                    if creditVerticalSpreadTest.matchOption(date=Option.get_followingThirdFriday()):
                        merged_json = {**merged_json,**{"description": creditVerticalSpreadTest.get_plain_English_Result()}}
                        print(Fore.GREEN)
                        logger.info(merged_json)
                        print(Fore.RESET)
                    else:
                        merged_json = {**merged_json,**{"description": "No match for %s" % stock['Ticker']}}
                        logger.info(merged_json)
                    merged_json = {**merged_json,**creditVerticalSpreadTest.to_dict()}
                    logger.debug(merged_json)
                    db.put_item( Item = merged_json)
                    response = db.get_item( Key = Key)
                    if 'Item' in response:
                        logger.info("info  stored for %s" % Key)
                        logger.debug("saved in table: %s" % response)
                    else:
                        raise MarketDataStorageFailedException()
                        
            except MarketDataStorageFailedException as e:
                logger.warning("Fail to get item from storage %s\n%s" % (Key,e))
            except MarketDataException as e:
                logger.warning("Fail to get options %s\n%s" % (Key,e))
            except ReadTimeout as e:
                logger.warning("Readtimeout for %s\n%s" % (Key,e))

except Exception as err:
    logger.error(
        "Unknow issue. Here's why: %s",
        err)
     # Get the current exception's traceback
    tb = traceback.format_exc()
    
    # Print the traceback, which includes the line number
    print("Traceback details:")
    print(tb)
