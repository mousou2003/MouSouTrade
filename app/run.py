import json
import sys
import traceback
import logging
import os
from requests import ReadTimeout
from colorama import Fore

from marketdata_clients.PolygonClient import *
from marketdata_clients.MarketDataClient import *
from engine.VerticalSpread import CreditSpread, DebitSpread
from engine.Options import *
from engine.data_model import *
from database.DynamoDB import DynamoDB

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Set the logging level to WARNING to suppress DEBUG messages
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('engine.VerticalSpread').setLevel(logging.WARNING)

class MissingEnvironmentVariableException(Exception):
    pass

class ConfigurationFileException(Exception):
    pass

def check_environment_variables(required_env_vars):
    env_vars = {var: os.getenv(var) for var in required_env_vars}
    missing_env_vars = [var for var, value in env_vars.items() if not value]
    if missing_env_vars:
        raise MissingEnvironmentVariableException(f"Missing required environment variables: {', '.join(missing_env_vars)}")
    return env_vars

def load_configuration_file(config_file):
    with open(config_file) as file:
        stocks = json.load(file)
        if isinstance(stocks, dict):
            stocks = [stocks]
    return stocks

def process_stock(stock, stock_number, number_of_stocks, dynamodb, table_name):
    try:
        ticker = stock.get('Ticker')
        if not ticker:
            raise KeyError('Ticker')
        logger.info(f"Processing stock {stock_number}/{number_of_stocks} :{ticker}")
        for direction in [BULLISH, BEARISH]:
            for strategy in [CREDIT, DEBIT]:
                spread_class = DebitSpread if strategy == DEBIT else CreditSpread
                spread = spread_class(underlying_ticker=ticker, direction=direction, strategy=strategy)

                target_expiration_date = Options.get_following_third_friday()
                key = {
                    "ticker": ticker,
                    "option": json.dumps({"date": target_expiration_date.strftime('%Y-%m-%d'), "direction": direction, "strategy": strategy}, default=str)
                }
                logger.info(f"Processing {strategy} {direction} spread for {ticker} for target date {target_expiration_date}")

                if spread.match_option(date=target_expiration_date):
                    merged_json = {**key, **{"description": spread.get_plain_english_result(), **spread.to_dict()}}
                    print(Fore.GREEN)
                    logger.info(merged_json)
                    print(Fore.RESET)
                else:
                    merged_json = {**key, **{"description": f"No match for {ticker}"}, **spread.to_dict()}
                    logger.info(merged_json)

                dynamodb.put_item(item=merged_json)
                response = dynamodb.get_item(key=key)
                if 'Item' in response:
                    logger.info("Info stored for %s" % key)
                    logger.debug("Saved in table: %s" % response)
                else:
                    raise MarketDataStrikeNotFoundException()
    except MarketDataException as e:
        logger.warning(f"Market data error for {ticker}: {e}")
    except ReadTimeout as e:
        logger.warning(f"Read timeout for {ticker}: {e}")
    except ConnectionRefusedError as e:
        logger.error(f"Connection refused: {e}")
    except KeyError as e:
        logger.warning(f"Error processing stock {stock_number}/{number_of_stocks}: Missing key {e}")
    except Exception as e:
        logger.warning(f"Error processing stock {stock.get('Ticker', 'N/A')}: {e}")
        traceback.print_exc()

def main():
    try:
        required_env_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION', 'MOUSOUTRADE_CONFIG_FILE', 'MOUSOUTRADE_STAGE']
        env_vars = check_environment_variables(required_env_vars)

        for var, value in env_vars.items():
            logger.debug(f"{var}: {value}")

        config_file = sys.argv[1] if len(sys.argv) > 1 else env_vars['MOUSOUTRADE_CONFIG_FILE']
        if not config_file:
            raise ConfigurationFileException("No configuration file provided and MOUSOUTRADE_CONFIG_FILE environment variable is not set.")
        
        table_name = env_vars['MOUSOUTRADE_STAGE']
        dynamodb = DynamoDB(table_name)
        stocks = load_configuration_file(config_file)
        number_of_stocks = len(stocks)

        for stock_number, stock in enumerate(stocks, start=1):
            process_stock(stock, stock_number, number_of_stocks, dynamodb, table_name)

        logger.info(f"Processed {number_of_stocks} stocks")
        return 0
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

if __name__ == "__main__":
    sys.exit(main())
