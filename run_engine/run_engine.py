import json
import sys
import traceback
import logging
import os  # Add import for os module
from requests import ReadTimeout
from colorama import Fore

from PolygoneClients.PolygoneClient import PolygoneClient
from MarketDataClients.MarketDataClient import *
from engine.Options import *
from engine.data_model import *
from database.src import Database

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Set the logging level to WARNING to suppress DEBUG messages
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

class MissingEnvironmentVariableException(Exception):
    pass

class ConfigurationFileException(Exception):
    pass

def main():
    try:
        # Check for required environment variables
        required_env_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION','MOUSOUTRADE_CONFIG_FILE']
        missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]

        if missing_env_vars:
            raise MissingEnvironmentVariableException(f"Missing required environment variables: {', '.join(missing_env_vars)}")

        # Print the values of the environment variables
        for var in required_env_vars:
            print(f"{var}: {os.getenv(var)}")

        # Determine the configuration file to use
        config_file = sys.argv[1] if len(sys.argv) > 1 else os.getenv('MOUSOUTRADE_CONFIG_FILE')
        if not config_file:
            raise ConfigurationFileException("No configuration file provided and MOUSOUTRADE_CONFIG_FILE environment variable is not set.")
        
        table_name = os.getenv('MOUSOUTRADE_STAGE', 'mousoutrade-dev')
        
        db = Database.Database(table_name)
        with open(config_file) as file:
            stocks = json.load(file)
            for stock in stocks:
                try:
                    for direction in [BULLISH, BEARISH]:  # Iterate through both bullish and bearish directions
                        for strategy in [CREDIT, DEBIT]:  # Iterate through both credit and debit strategies

                            spread_class = DebitSpread if strategy == DEBIT else CreditSpread
                            spread = spread_class(underlying_ticker=stock['Ticker'], direction=direction,
                                                   strategy=strategy, client=PolygoneClient())

                            if spread.matchOption(date=Option.get_followingThirdFriday()):
                                Key = {
                                    "ticker": stock['Ticker'],
                                    "option": json.dumps({"date": spread.get_expiration_date().strftime('%Y-%m-%d'), "direction": direction,
                                                      "strategy": strategy}, default=str)
                                }
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
                                Key = {
                                    "ticker": stock['Ticker'],
                                    "option": json.dumps({"date": spread.get_expiration_date().strftime('%Y-%m-%d'), "direction": direction,
                                                      "strategy": strategy}, default=str)
                                }
                                merged_json = {**Key, **{"description": f"No match for {stock['Ticker']}"},
                                               **spread.to_dict()}
                                logger.info(merged_json)
                            
                            db.put_item(Item=merged_json)
                            response = db.get_item(Key=Key)
                            if 'Item' in response:
                                logger.info("info stored for %s" % Key)
                                logger.debug("saved in table: %s" % response)
                            else:
                                raise MarketDataStrikeNotFoundException()
                                    
                except MarketDataException as e:
                    logger.warning("Fail to get options %s\n%s" % (Key, e))
                except ReadTimeout as e:
                    logger.warning("Readtimeout for %s\n%s" % (Key, e))
                except ConnectionRefusedError as e:
                    logger.error(f"Connection refused: {e}")
                except Exception as e:
                    logger.warning(f"Error processing stock {stock.get('Ticker', 'N/A')}: {e}")
                    traceback.print_exc()

    except FileNotFoundError:
        logger.error("Input file not found.")
        return 1
    except json.JSONDecodeError:
        logger.error("Invalid JSON in input file.")
        return 1
    except ConnectionRefusedError as e:
        logger.error(f"Connection refused: {e}")
        return 1
    except MissingEnvironmentVariableException as e:
        logger.error(e)
        return 1
    except ConfigurationFileException as e:
        logger.error(e)
        return 1
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        traceback.print_exc()
        return 1

def lambda_handler(event, context):
    input_file = '/tmp/input.json'
    with open(input_file, 'w') as file:
        json.dump(event, file)
    sys.argv = [sys.argv[0], input_file]
    main()

if __name__ == "__main__":
    sys.exit(main())
