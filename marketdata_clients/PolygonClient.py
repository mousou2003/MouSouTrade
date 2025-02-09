import polygon
import time
import logging
import asyncio
from marketdata_clients.MarketDataClient import *

logger = logging.getLogger(__name__)

class PolygonClient(MarketDataClient):
    THROTTLE_LIMIT = 60 / 5  # we are currently limited to 5 requests per minutes
    CLIENT_NAME = "polygone"
    options_client = None
    stocks_client = None

    def __new__(cls):
        if PolygonClient.instance is None:
            logger.info("Creating PolygoneClient Singleton")
            PolygonClient.instance = super(PolygonClient, cls).__new__(cls)
            PolygonClient.create_polygone_clients()
            logger.info("PolygoneClient Singleton created")
        return PolygonClient.instance

    def __init__(self) -> None:
        if PolygonClient.instance is None:
            logger.info("Init PolygoneClient")
            super().__init__()
            logger.info("Clients successfully created")

    def __str__(self):
        return self.__class__.__name__

    def create_polygone_clients():
        PolygonClient.load_key_secret(
            jsonfile="./config/SecurityKeys.json", stage="Sandbox", client_name=PolygonClient.CLIENT_NAME)
        PolygonClient.options_client = polygon.OptionsClient(PolygonClient._my_key)
        PolygonClient.stocks_client = polygon.StocksClient(PolygonClient._my_key)

    def get_previous_stock_close(self, ticker):
        self.wait_for_no_throttle()
        try:
            response = self.stocks_client.get_previous_close(ticker)
            if 'results' not in response or not response['results']:
                raise KeyError('results')
            return response['results'][0]['c']
        except KeyError as err:
            raise MarketDataException(f"No results found for ticker {ticker}", err)

    def get_daily_open_close(self, ticker, date):
        self.wait_for_no_throttle()
        try:
            response = self.stocks_client.get_daily_open_close(symbol=ticker, date=date)
            if 'results' not in response or not response['results']:
                raise KeyError('results')
            return response['results']
        except KeyError as err:
            raise MarketDataException(f"No results found for ticker {ticker} on {date}", err)
        except Exception as err:
            raise MarketDataException(f"Failed to get daily open close for {ticker} on {date}", err)

    def get_grouped_option_daily_bars(self, date):
        self.wait_for_no_throttle()
        try:
            response = self.options_client.get_grouped_daily_bars(date)
            if 'results' not in response or not response['results']:
                raise KeyError('results')
            return response['results']
        except KeyError as err:
            raise MarketDataStrikeNotFoundException(f"No results found for date {date}", err)
        except Exception as err:
            raise MarketDataException(f"Failed to get grouped option daily bars for {date}", err)

    def get_option_previous_close(self, ticker):
        self.wait_for_no_throttle()
        try:
            response = self.options_client.get_previous_close(ticker)
            if 'results' not in response or not response['results']:
                raise KeyError('results')
            return response['results'][0]['c']
        except KeyError as err:
            raise MarketDataStrikeNotFoundException(f"No results found for ticker {ticker}", err)
        except Exception as err:
            raise MarketDataException(f"Failed to get previous close price for Option {ticker}", err)

    async def async_get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self.wait_for_no_throttle()
        try:
            contracts = polygon.ReferenceClient(PolygonClient._my_key).get_option_contracts(
                underlying_ticker=underlying_ticker,
                expiration_date_lte=expiration_date_lte,
                expiration_date_gte=expiration_date_gte,
                contract_type=contract_type,
                order=order,
                sort='strike_price'
            )
            if 'results' not in contracts or not contracts['results']:
                raise KeyError('results')
            return contracts['results']
        except KeyError as err:
            raise MarketDataException(f"No option contracts found for {underlying_ticker}", err)
        except Exception as err:
            raise MarketDataException(f"Failed to asynchronously get option contracts for {underlying_ticker}", err)

    def get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self.wait_for_no_throttle()
        try:
            return asyncio.run(self.async_get_option_contracts(underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order))
        except Exception as err:
            raise MarketDataException(f"Failed to get option contracts for {underlying_ticker}", err)

    def convert_option_symbol_formats(self, ticker):
        try:
            return polygon.convert_option_symbol_formats(ticker, from_format=PolygonClient.CLIENT_NAME, to_format='tos')
        except Exception as err:
            raise MarketDataException(f"Failed to convert option symbol formats for {ticker}", err)

    def wait_for_no_throttle(self):
        time.sleep(self.THROTTLE_LIMIT)
