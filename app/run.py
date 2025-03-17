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
from datetime import date, datetime, timedelta

from marketdata_clients.BaseMarketDataClient import MarketDataException, MarketDataStrikeNotFoundException
from marketdata_clients.PolygonClient import POLYGON_CLIENT_NAME
from marketdata_clients.MarketDataClient import *
from engine.VerticalSpread import CreditSpread, DebitSpread, VerticalSpread, VerticalSpreadMatcher
from engine.Options import *
from engine.Stocks import Stocks
from engine.data_model import *
from database.DynamoDB import DynamoDB
from config.ConfigLoader import ConfigLoader
from agents.trading_agent import TradingAgent

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
# logging.getLogger('engine.ContractSelector').setLevel(logging.DEBUG)
# logging.getLogger('engine.ContractSelector').addHandler(handler)
#logging.getLogger('engine.VerticalSpread').setLevel(logging.DEBUG)
# logging.getLogger('engine.VerticalSpread').addHandler(handler)
# # logging.getLogger('engine.Options').setLevel(logging.DEBUG)
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

def process_stock(market_data_client: IMarketDataClient, stock: Stocks, 
                 stock_number: int, number_of_stocks: int,
                 target_expiration_date: date, agent: TradingAgent, 
                 dynamodb: DynamoDB) -> List[VerticalSpread]:
    """Process stock and return list of spreads"""
    ticker = stock['Ticker']
    if not ticker:
        raise KeyError('Ticker')

    spreads = []
    today = datetime.today().date()
    
    # First get existing spreads for this ticker and expiration
    existing_spreads = dynamodb.query_spreads(
        ticker=ticker, 
        expiration_date=target_expiration_date
    )

    # Get option snapshots first as they're needed for both new spreads and trading
    all_snapshots = {}
    for direction in [DirectionType.BULLISH, DirectionType.BEARISH]:
        for strategy in [StrategyType.CREDIT, StrategyType.DEBIT]:
            contracts = market_data_client.get_option_contracts(
                underlying_ticker=ticker,
                expiration_date_gte=target_expiration_date,
                expiration_date_lte=target_expiration_date,
                contract_type=Options.get_contract_type(strategy, direction),
                order=Options.get_order(strategy=strategy, direction=direction)
            )
            snapshots = build_options_snapshots(market_data_client, contracts, ticker)
            all_snapshots.update(snapshots)

    if not existing_spreads:
        # Generate new spreads for this stock
        for direction in [DirectionType.BULLISH, DirectionType.BEARISH]:
            for strategy in [StrategyType.CREDIT, StrategyType.DEBIT]:
                logger.info(f"Processing stock {stock_number}/{number_of_stocks} {strategy.value} {direction.value} spread for {ticker} for target date {target_expiration_date}")

                contracts = market_data_client.get_option_contracts(
                    underlying_ticker=ticker,
                    expiration_date_gte=target_expiration_date,
                    expiration_date_lte=target_expiration_date,
                    contract_type=Options.get_contract_type(strategy, direction),
                    order=Options.get_order(strategy=strategy, direction=direction)
                )

                spread_result = VerticalSpreadMatcher.match_option(
                    options_snapshots=all_snapshots, 
                    underlying_ticker=ticker, 
                    direction=direction, 
                    strategy=strategy, 
                    previous_close=stock['close'], 
                    date=target_expiration_date, 
                    contracts=contracts
                )
                
                if spread_result and spread_result.matched:
                    success, guid = dynamodb.set_spreads(spread=spread_result)
                    if success:
                        spreads.append(spread_result)
    else:
        # Use existing spreads but update their snapshots
        for spread in existing_spreads:
            # Update snapshots for both legs if contracts exist
            if spread.first_leg_contract:
                first_leg_snapshot = all_snapshots.get(spread.first_leg_contract.ticker)
                if first_leg_snapshot:
                    spread.first_leg_snapshot = first_leg_snapshot
            if spread.second_leg_contract:
                second_leg_snapshot = all_snapshots.get(spread.second_leg_contract.ticker)
                if second_leg_snapshot:
                    spread.second_leg_snapshot = second_leg_snapshot
            spreads.append(spread)

    # Process spreads through trading agent
    if spreads:
        agent.run(spreads)
        # Update spreads in DynamoDB after agent processing
        for spread in spreads:
            dynamodb.set_spreads(spread=spread)

    return spreads

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
        required_env_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION', 
                             'MOUSOUTRADE_CONFIG_FILE', 'MOUSOUTRADE_STAGE',
                             'MOUSOUTRADE_CLIENTS']
        env_vars = check_environment_variables(required_env_vars)

        for var, value in env_vars.items():
            logger.debug(f"{var}: {value}")

        config_file = sys.argv[1] if len(sys.argv) > 1 else env_vars['MOUSOUTRADE_CONFIG_FILE']
        if not config_file:
            raise ConfigurationFileException("No configuration file provided and MOUSOUTRADE_CONFIG_FILE environment variable is not set.")
        
        stage = env_vars['MOUSOUTRADE_STAGE']
        
        stocks = load_configuration_file(config_file)
        number_of_stocks = len(stocks)
        
        clients = env_vars['MOUSOUTRADE_CLIENTS']
        market_data_client = MarketDataClient(config_file='./config/SecurityKeys.json', stage=stage, client_name=clients)
        marketdata_stocks = Stocks(market_data_client=market_data_client)

        # Set target date once
        target_expiration_date = date(2025, 4, 11)

        # Initialize trading agent without DynamoDB dependency
        agent = TradingAgent()
        all_spreads = []

        # Create DynamoDB instance for persistence
        dynamodb = DynamoDB(stage)
        initial_count = dynamodb.count_items()

        # Process stocks and collect spreads
        for stock_number, stock in enumerate(stocks, start=1):
            ticker = stock.get('Ticker')
            if ticker in marketdata_stocks.stocks_data:
                try:
                    stock.update(marketdata_stocks.stocks_data[ticker])
                    stock_spreads = process_stock(
                        market_data_client=market_data_client, 
                        stock=stock, 
                        stock_number=stock_number, 
                        number_of_stocks=number_of_stocks,
                        target_expiration_date=target_expiration_date,
                        agent=agent,
                        dynamodb=dynamodb  # Pass DynamoDB instance
                    )
                    all_spreads.extend(stock_spreads)
                except Exception as e:
                    logger.error(f"Error processing {ticker}: {e}")

        # Save final performance metrics with date as string
        daily_performance = {
            "date": date.today().strftime('%Y-%m-%d'),  # Convert date to string
            "total_spreads": len(all_spreads),
            "active_trades": len(agent.active_spreads),
            "completed_trades": len(agent.completed_spreads)
        }
        dynamodb.update_daily_performance(daily_performance)

        # Print summary
        logger.info(f"Total spreads generated: {len(all_spreads)}")
        logger.info(f"Active trades: {len(agent.active_spreads)}")
        logger.info(f"Completed trades: {len(agent.completed_spreads)}")
        
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
