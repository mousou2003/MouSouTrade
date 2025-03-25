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
from botocore.exceptions import EndpointConnectionError

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
    loglevel = logging.INFO
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
            raise
    return options_snapshots

def process_stock(market_data_client: IMarketDataClient, stock: Stock,
                 stock_number: int, number_of_stocks: int,
                 target_expiration_date: date, agent: TradingAgent, 
                 dynamodb: DynamoDB) -> Tuple[List[VerticalSpread], int, int]:
    """Process stock and return (spreads, generated_count, updated_count)"""
    generated_count = 0
    updated_count = 0
    spreads = []
    logger.info(f"Starting to process stock {stock.ticker} ({stock_number}/{number_of_stocks})")
    if not stock.ticker:
        raise KeyError('Ticker')

    today = datetime.today().date()
    
    logger.info(f"Querying existing spreads for {stock.ticker} expiring on {target_expiration_date}")
    existing_spreads = dynamodb.query_spreads(
        ticker=stock.ticker
    )
    logger.info(f"Found {len(existing_spreads) if existing_spreads else 0} existing spreads")

    logger.info(f"Fetching option snapshots for {stock.ticker}")
    all_snapshots = {}
    contracts = [Contract]
    for direction in [DirectionType.BULLISH, DirectionType.BEARISH]:
        for strategy in [StrategyType.CREDIT, StrategyType.DEBIT]:
            contracts = market_data_client.get_option_contracts(
                underlying_ticker=str(stock.ticker),
                expiration_date_gte=(target_expiration_date - timedelta(days=6)).strftime('%Y-%m-%d'),
                expiration_date_lte=target_expiration_date.strftime('%Y-%m-%d'),
                contract_type=Options.get_contract_type(strategy, direction).value,
                order=Options.get_order(strategy=strategy, direction=direction).value
            )
            snapshots= build_options_snapshots(contracts=contracts, market_data_client=market_data_client,
                underlying_ticker=stock.ticker)
            all_snapshots.update(snapshots)
    if len(contracts) == 0:
        logger.info(f"No contracts found for {stock.ticker} expiring on {target_expiration_date}")
        return [], 0, 0
    if not existing_spreads:
        logger.info(f"No existing spreads found for {stock.ticker}, generating new ones")
        # Generate new spreads for this stock
        for direction in [DirectionType.BULLISH, DirectionType.BEARISH]:
            for strategy in [StrategyType.CREDIT, StrategyType.DEBIT]:
                logger.info(f"Processing stock {stock_number}/{number_of_stocks} {strategy.value} {direction.value} spread for {stock.ticker} for target date {target_expiration_date}")

                spread_result = VerticalSpreadMatcher.match_option(
                    options_snapshots=all_snapshots, 
                    underlying_ticker=stock.ticker, 
                    direction=direction, 
                    strategy=strategy, 
                    previous_close=stock.close,
                    date = contracts[0].expiration_date,
                    contracts=contracts
                )
                
                if spread_result and spread_result.matched:
                    spread_result.stock = stock  # Set stock data after creation
                    logger.info(f"Found matching {strategy.value} {direction.value} spread for {stock.ticker}")
                    success, guid = dynamodb.set_spreads(spread=spread_result)
                    if success:
                        logger.info(f"Successfully saved spread {guid} to database")
                        spreads.append(spread_result)
                        generated_count += 1
    else:
        logger.info(f"Updating {len(existing_spreads)} existing spreads for {stock.ticker}")
        # Use existing spreads but update their snapshots
        for spread in existing_spreads:
            spread.stock = stock
            VerticalSpread.update_snapshots(spread,all_snapshots)
            spreads.append(spread)
        updated_count = len(existing_spreads)

    # Process all spreads at once through trading agent
    if spreads:
        modified_spreads = agent.run(spreads, current_date=today)  # Pass current date to agent
        # Only update spreads that were modified by the agent
        for spread in modified_spreads:
            dynamodb.set_spreads(spread=spread)
            logger.debug(f"Updated spread {spread.spread_guid} status: {spread.agent_status}")

    return spreads, generated_count, updated_count

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
        logger.info("Debug mode enabled, waiting for debugger...")
        wait_for_debugger("localhost", 5678)

    try:
        logger.info("Starting MouSouTrade application")
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
        
        logger.info(f"Loading configuration from {config_file}")
        stocks = load_configuration_file(config_file)
        number_of_stocks = len(stocks)
        logger.info(f"Found {number_of_stocks} stocks to process")
        
        clients = env_vars['MOUSOUTRADE_CLIENTS']
        logger.info(f"Initializing market data client with {clients}")
        market_data_client = MarketDataClient(config_file='./config/SecurityKeys.json', stage=stage, client_name=clients)
        marketdata_stocks = Stocks(market_data_client=market_data_client)

        # Set target date once
        target_expiration_date = Options.get_next_friday(datetime.today().date())
        logger.info(f"Target expiration date set to {target_expiration_date}")
        logger.info("Initializing trading agent and DynamoDB")
        # Initialize trading agent with current date
        agent = TradingAgent(current_date=datetime.today())  # Set initial current_date
        
        # Initialize counters
        generated_spreads = 0
        updated_spreads = 0
        all_spreads = []
        total_generated = 0
        total_updated = 0

        # Create DynamoDB instance for persistence
        dynamodb = DynamoDB(stage)
        initial_count = dynamodb.count_items()
        logger.info(f"Initial database count: {initial_count} items")

        # Process stocks and collect spreads
        for stock_number, stock_config in enumerate(stocks, start=1):
            ticker = stock_config.get('Ticker')
            if ticker:
                logger.info(f"\n{'='*50}\nProcessing stock {ticker} ({stock_number}/{number_of_stocks})\n{'='*50}")
                try:
                    stocks = marketdata_stocks.get_daily_bars(ticker)
                    if stocks:  # Check if we got any data back
                        current_stock = stocks[0]  # Get most recent data
                        stock_spreads, generated, updated = process_stock(
                            market_data_client=market_data_client, 
                            stock=current_stock,
                            stock_number=stock_number, 
                            number_of_stocks=number_of_stocks,
                            target_expiration_date=target_expiration_date,
                            agent=agent,
                            dynamodb=dynamodb
                        )
                        if stock_spreads:
                            all_spreads.extend(stock_spreads)
                            total_generated += generated
                            total_updated += updated
                except Exception as e:
                    logger.error(f"Error processing {ticker}: {e}")
                    logger.error(f"Stack trace for {ticker}:", exc_info=True)

        final_count = dynamodb.count_items()
        logger.info(f"Database items change: {final_count - initial_count} new items")
        
        # Get daily performance from trading agent
        daily_performance = agent.get_daily_performance()
        # Add generated/updated counts
        daily_performance.update({
            "total_spreads": len(all_spreads),
            "generated_spreads": total_generated,
            "updated_spreads": total_updated,
        })
        dynamodb.update_daily_performance(daily_performance)

        # Print updated summary using agent metrics
        logger.info("Daily Performance Summary:")
        for key, value in daily_performance.items():
            logger.info(f"{key}: {value}")
        
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
    except EndpointConnectionError as e:
        logger.error(f"Failed to connect to AWS endpoint: {e}")
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
