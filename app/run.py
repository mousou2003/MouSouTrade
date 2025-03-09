import json
import sys
import traceback
import logging
import os
import time
import socket
from requests import ReadTimeout
from colorama import Fore, Style
from decimal import Decimal

from marketdata_clients.BaseMarketDataClient import MarketDataException, MarketDataStrikeNotFoundException
from marketdata_clients.PolygonClient import POLYGON_CLIENT_NAME
from marketdata_clients.MarketDataClient import *
from engine.VerticalSpread import CreditSpread, DebitSpread
from engine.Options import *
from engine.Stocks import Stocks
from engine.data_model import *
from database.DynamoDB import DynamoDB
from config.ConfigLoader import ConfigLoader

logger = logging.getLogger(__name__)
debug_mode = os.getenv("DEBUG_MODE")
if (debug_mode and debug_mode.lower() == "true"):
    loglevel = logging.DEBUG
else:
    loglevel = logging.WARNING
logging.basicConfig(level=loglevel)
class ColorFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.WARNING:
            record.msg = f"{Fore.YELLOW}{record.msg}{Style.RESET_ALL}"
        elif record.levelno == logging.ERROR:
            record.msg = f"{Fore.RED}{record.msg}{Style.RESET_ALL}"
        return super().format(record)
handler = logging.StreamHandler()
handler.setFormatter(ColorFormatter())
logger.addHandler(handler)

# Set the logging level to WARNING to suppress DEBUG messages
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)
# logging.getLogger('engine.VerticalSpread').setLevel(logging.DEBUG)
# logging.getLogger('engine.VerticalSpread').addHandler(handler)
# logging.getLogger('engine.Options').setLevel(logging.DEBUG)
# logging.getLogger('engine.Options').addHandler(handler)
# logging.getLogger('engine.Stocks').setLevel(logging.INFO)
# logging.getLogger('engine.Stocks').addHandler(handler)
#logging.getLogger('marketdata_clients.MarketDataClient').setLevel(logging.INFO)
# logging.getLogger('marketdata_clients.MarketDataClient').addHandler(handler)
# logging.getLogger('marketdata_clients.PolygonClient').setLevel(logging.INFO)
# logging.getLogger('marketdata_clients.PolygonClient').addHandler(handler)
#logging.getLogger('marketdata_clients.ETradeClient').setLevel(logging.INFO)
# logging.getLogger('marketdata_clients.ETradeClient').addHandler(handler)


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
    try:
        with open(config_file) as file:
            stocks = json.load(file)
            if isinstance(stocks, dict):
                stocks = [stocks]
        return stocks
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_file}")
        raise

def build_options_snapshots(market_data_client: IMarketDataClient, contracts: list[Contract], underlying_ticker:str) -> dict:
    options_snapshots = {}
    for contract in contracts:
        try:
            options_snapshot = market_data_client.get_option_snapshot(underlying_ticker=underlying_ticker, option_symbol=contract.ticker)
            options_snapshots[contract.ticker] = options_snapshot
        except (MarketDataException, KeyError, TypeError) as e:
            logger.warning(f"{type(e).__name__} - {e}\n {e.inner_exception}")
            continue
    return options_snapshots

def process_stock(market_data_client, stock, stock_number, number_of_stocks, dynamodb, stage):
    ticker = stock['Ticker']
    if not ticker:
        raise KeyError('Ticker')
    
    ideal_expiration = datetime.today() + timedelta(weeks=4)    
    target_expiration_date = Options.get_next_friday(ideal_expiration).date()

    for direction in [DirectionType.BULLISH, DirectionType.BEARISH]:
        for strategy in [StrategyType.CREDIT, StrategyType.DEBIT]:
            contracts = market_data_client.get_option_contracts(
                underlying_ticker=ticker,
                expiration_date_gte=target_expiration_date,
                expiration_date_lte=target_expiration_date,
                contract_type=Options.get_contract_type(strategy, direction),
                order=Options.get_order(strategy=strategy, direction=direction)
            )
            options_snapshots = build_options_snapshots(market_data_client, contracts, ticker)

            spread_class = DebitSpread if strategy == StrategyType.DEBIT else CreditSpread
            spread = spread_class()

            logger.info(f"Processing stock {stock_number}/{number_of_stocks} {strategy.value} {direction.value} spread for {ticker} for target date {target_expiration_date}")

            matched = spread.match_option(options_snapshots=options_snapshots, underlying_ticker=ticker, 
                                          direction=direction, strategy=strategy, previous_close=stock['close'], 
                                          date=target_expiration_date, contracts=contracts)
            key = {
                "ticker": f"{spread.underlying_ticker};{spread.expiration_date.strftime(DataModelBase.DATE_FORMAT)};{spread.update_date.strftime(DataModelBase.DATE_FORMAT)}",
                "option": json.dumps({"date": target_expiration_date.strftime(DataModelBase.DATE_FORMAT), 
                                      "direction": direction.value, 
                                      "strategy": strategy.value}, default=str)
            }
            merged_json = {**key, **{"description": spread.get_description() if matched else f"No match for {ticker}"}, 
                           **spread.to_dict()}
            print(f"Match {'found' if matched else 'NOT found'}, and stored in {key}")
            logger.debug(merged_json)
            dynamodb.put_item(item=merged_json)
            response = dynamodb.get_item(key=key)
            if 'Item' in response:
                validated_records = spread.from_dict(response['Item']).to_dict()
                logger.debug(f'Item saved in table:\n{validated_records}')
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
        
        stage = env_vars['MOUSOUTRADE_STAGE']
        dynamodb = DynamoDB(stage)
        stocks = load_configuration_file(config_file)
        number_of_stocks = len(stocks)
        
        market_data_client = MarketDataClient(config_file='./config/SecurityKeys.json', stage=stage)
        marketdata_stocks = Stocks(market_data_client=market_data_client)

        for stock_number, stock in enumerate(stocks, start=1):
            ticker = stock.get('Ticker')
            if ticker in marketdata_stocks.stocks_data:
                try:
                    stock.update(marketdata_stocks.stocks_data[ticker])
                    process_stock(market_data_client=market_data_client, stock=stock, 
                                  stock_number=stock_number, number_of_stocks=number_of_stocks, 
                                  dynamodb=dynamodb, stage=stage)
                except ReadTimeout as e:
                    logger.warning(f"Read timeout for {ticker}: {e}")
                except ConnectionRefusedError as e:
                    logger.exception(f"Connection refused for {ticker}: {e}")
                    raise e
                except (KeyError, MarketDataException) as e:
                    logger.exception(f"Error processing stock {stock_number}/{number_of_stocks} ({ticker}): {e}")
            else:
                logger.warning(f"Stock {stock_number}/{number_of_stocks} ({ticker}) not found in market")
        print(f"Number of stocks in initial config file: {number_of_stocks}")
        print(f"Number of stocks found in marketdata_stocks: {len(marketdata_stocks.stocks_data)}")
        print(f"Processed {number_of_stocks} stocks")
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
