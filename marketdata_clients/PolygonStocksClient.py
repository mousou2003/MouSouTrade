import polygon
import logging
import time
from marketdata_clients.PolygonClient import PolygonClient
from marketdata_clients.MarketDataClient import *

logger = logging.getLogger(__name__)

class PolygonStocksClient(PolygonClient):
    client = None
    DEFAULT_THROTTLE_LIMIT = 12

    def __new__(cls, throttle_limit=DEFAULT_THROTTLE_LIMIT):
        if PolygonStocksClient.instance is None:
            logger.debug("Creating PolygonStocksClient Singleton")
            PolygonStocksClient.instance = super(PolygonStocksClient, cls).__new__(cls)
            try:
                PolygonStocksClient.THROTTLE_LIMIT = throttle_limit
                PolygonStocksClient.instance.client = polygon.StocksClient(PolygonStocksClient.instance._my_key)
                logger.debug("PolygonStocksClient Singleton created")
            except Exception as e:
                logger.error(f"Failed to create PolygonStocksClient: {e}")
                raise
        return PolygonStocksClient.instance

    def get_previous_stock_close(self, ticker):
        self.wait_for_no_throttle()
        retries = 3
        for attempt in range(retries):
            try:
                response = self.client.get_previous_close(ticker)
                if 'results' not in response or not response['results']:
                    raise KeyError('results')
                return response['results'][0]['c']
            except KeyError as err:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise MarketDataException(f"No results found for ticker {ticker}", err)
            except Exception as err:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise MarketDataException(f"Failed to get previous stock close for {ticker}", err)

    def get_grouped_daily_bars(self, date):
        self.wait_for_no_throttle()
        retries = 3
        for attempt in range(retries):
            try:
                response = PolygonStocksClient.client.get_grouped_daily_bars(date=date)
                if 'results' not in response or not response['results']:
                    raise KeyError('results')
                return response['results']
            except KeyError as err:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise MarketDataException(f"No results found on {date}", err)
            except Exception as err:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise MarketDataException(f"Failed to get daily open close on {date}", err)
