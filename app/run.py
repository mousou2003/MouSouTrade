import json
import sys
import traceback
import logging
import os
import time
import socket
from requests import ReadTimeout
from colorama import Fore
from decimal import Decimal

from marketdata_clients.PolygonClient import *
from marketdata_clients.MarketDataClient import *
from engine.VerticalSpread import CreditSpread, DebitSpread
from engine.Options import *
from engine.Stocks import Stocks
from engine.data_model import *
from database.DynamoDB import DynamoDB

logger = logging.getLogger(__name__)
if os.getenv("DEBUG_MODE") != "true":
    loglevel = logging.DEBUG
else:
    loglevel = logging.INFO
logging.basicConfig(level=logging.INFO)

# Set the logging level to WARNING to suppress DEBUG messages
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('engine.VerticalSpread').setLevel(logging.DEBUG)

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
    ticker = stock.get('Ticker')
    if not ticker:
        raise KeyError('Ticker')
    
    ideal_expiration = datetime.datetime.today() + datetime.timedelta(weeks=5)    
    target_expiration_date = Options.get_next_friday(ideal_expiration).date()

    for direction in [BULLISH, BEARISH]:
        for strategy in [CREDIT, DEBIT]:
            spread_class = DebitSpread if strategy == DEBIT else CreditSpread
            spread = spread_class(underlying_ticker=ticker, direction=direction, strategy=strategy,
                                  previous_close=Decimal(stock['close']))
            
            key = {
                "ticker": ticker,
                "option": json.dumps({"date": target_expiration_date.strftime('%Y-%m-%d'), "direction": direction, "strategy": strategy}, default=str)
            }

            logger.info(f"Processing stock {stock_number}/{number_of_stocks} {strategy} {direction} spread for {ticker} for target date {target_expiration_date}")
            matched = spread.match_option(date=target_expiration_date)
            if matched:
                merged_json = {**key, **{"description": spread.get_description(), **spread.to_dict()}}
                logger.debug(merged_json)
            else:
                merged_json = {**key, **{"description": f"No match for {ticker}"}, **spread.to_dict()}
                logger.debug(merged_json)

            dynamodb.put_item(item=merged_json)
            response = dynamodb.get_item(key=key)
            if 'Item' in response:
                logger.info("Match %sfound, and stored in %s" % (("", key) if matched else ("not ", key)))
                logger.debug("Saved in table: %s" % response)
            else:
                raise MarketDataStrikeNotFoundException(f"No item found for ticker {ticker}")

def wait_for_debugger(host, port, timeout=60):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                print(f"Debugger is available on {host}:{port}")
                return True
        except (ConnectionRefusedError, socket.timeout):
            print(f"Waiting for debugger to be available on {host}:{port}...")
            time.sleep(1)
    print(f"Timeout waiting for debugger on {host}:{port}")
    return False

def main():
    if os.getenv("DEBUG_MODE") == "true":
        wait_for_debugger("localhost", 5678)
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

        marketdata_stocks = Stocks()

        for stock_number, stock in enumerate(stocks, start=1):
            ticker = stock.get('Ticker')
            if ticker in marketdata_stocks.stocks_data:
                stock.update(marketdata_stocks.get_daily_bars(ticker))
                try:
                    process_stock(stock, stock_number, number_of_stocks, dynamodb, table_name)
                except ReadTimeout as e:
                    logger.warning(f"Read timeout for {ticker}: {e}")
                except ConnectionRefusedError as e:
                    logger.exception(f"Connection refused for {ticker}: {e}")
                    raise e
                except (KeyError, MarketDataException) as e:
                    logger.exception(f"Error processing stock {stock_number}/{number_of_stocks} ({ticker}): {e}")
        logger.info(f"Number of stocks in initial config file: {number_of_stocks}")
        logger.info(f"Number of stocks found in marketdata_stocks: {len(marketdata_stocks.stocks_data)}")
        logger.info(f"Processed {number_of_stocks} stocks")
        return 0
    except FileNotFoundError:
        logger.error("Input file not found.")
        return 1
    except json.JSONDecodeError:
        logger.error("Invalid JSON in input file.")
        return 1
    except ConnectionRefusedError as e:
        logger.error(f"Connection refused: {e.with_traceback(None)}")
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
