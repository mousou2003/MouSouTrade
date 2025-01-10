import json
import sys
import traceback
import logging
import calendar
import datetime
import operator
from colorama import Fore

from requests import ReadTimeout

from PolygoneClients.PolygoneClient import PolygoneClient
from MarketDataClients.MarketDataClient import *
from engine.Options import *
from engine.data_model import *
from database.src import Database


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def main():
    try:
        db =  Database.Database("Beta")
        with open(sys.argv[1]) as file:
            stocks = json.load(file)
            for stock in stocks:
                try:
                    for direction in [BULLISH, BEARISH]:  # Iterate through both bullish and bearish directions
                        for strategy in [CREDIT, DEBIT]:  # Iterate through both credit and debit strategies

                            Key = {
                                "ticker": stock['Ticker'],
                                "option": json.dumps({"date": datetime.date.today(), "direction": direction,
                                                      "strategy": strategy}, default=str)
                            }

                            if 'Item' in db.get_item(Key=Key):
                                logger.info("info already stored for %s" % Key)
                                continue  # Skip if data already exists

                            spread_class = DebitSpread if strategy == DEBIT else CreditSpread
                            spread = spread_class(underlying_ticker=stock['Ticker'], direction=direction,
                                                   strategy=strategy, client=PolygoneClient())

                            if spread.matchOption(date=Option.get_followingThirdFriday()):
                                merged_json = {**Key, **{"description": spread.get_plain_English_Result(),
                                                         **spread.to_dict()}}
                                print(Fore.GREEN)
                                logger.info(merged_json)
                                print(Fore.RESET)
                                db.put_item(Item=merged_json)
                                response = db.get_item(Key=Key)
                                if 'Item' in response:
                                    logger.info("info stored for %s" % Key)
                                else:
                                    raise MarketDataStorageFailedException("Failed to store item in database")
                            else:
                                merged_json = {**Key, **{"description": f"No match for {stock['Ticker']}"},
                                               **spread.to_dict()}
                                logger.info(merged_json)
                            
                            db.put_item( Item = merged_json)
                            response = db.get_item( Key = Key)
                            if 'Item' in response:
                                logger.info("info  stored for %s" % Key)
                                logger.debug("saved in table: %s" % response)
                            else:
                                raise MarketDataStrikeNotFoundException()
                                    
                except MarketDataException as e:
                    logger.warning("Fail to get options %s\n%s" % (Key,e))
                except ReadTimeout as e:
                    logger.warning("Readtimeout for %s\n%s" % (Key,e))
                except Exception as e:
                    logger.warning(f"Error processing stock {stock.get('Ticker', 'N/A')}: {e}")
                    traceback.print_exc()

    except FileNotFoundError:
        logger.error("Input file not found.")
    except json.JSONDecodeError:
        logger.error("Invalid JSON in input file.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()