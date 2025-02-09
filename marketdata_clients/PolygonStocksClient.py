import polygon
import logging
from marketdata_clients.PolygonClient import PolygonClient
from marketdata_clients.MarketDataClient import *

logger = logging.getLogger(__name__)

class PolygonStocksClient(PolygonClient):
    client = None
    DEFAULT_THROTTLE_LIMIT = 12

    def __new__(cls, throttle_limit=DEFAULT_THROTTLE_LIMIT):
        if PolygonStocksClient.instance is None:
            logger.info("Creating PolygonStocksClient Singleton")
            PolygonStocksClient.instance = super(PolygonStocksClient, cls).__new__(cls)
            try:
                PolygonStocksClient.THROTTLE_LIMIT = throttle_limit
                PolygonStocksClient.instance.client = polygon.StocksClient(PolygonStocksClient.instance._my_key)
                logger.info("PolygonStocksClient Singleton created")
            except Exception as e:
                logger.error(f"Failed to create PolygonStocksClient: {e}")
                raise
        return PolygonStocksClient.instance

    def get_previous_stock_close(self, ticker):
        self.wait_for_no_throttle()
        try:
            response = self.client.get_previous_close(ticker)
            if 'results' not in response or not response['results']:
                raise KeyError('results')
            return response['results'][0]['c']
        except KeyError as err:
            raise MarketDataException(f"No results found for ticker {ticker}", err)
        except Exception as err:
            raise MarketDataException(f"Failed to get previous stock close for {ticker}", err)

    def get_daily_open_close(self, ticker, date):
        self.wait_for_no_throttle()
        try:
            response = PolygonStocksClient.client.get_daily_open_close(symbol=ticker, date=date)
            if 'results' not in response or not response['results']:
                raise KeyError('results')
            return response['results']
        except KeyError as err:
            raise MarketDataException(f"No results found for ticker {ticker} on {date}", err)
        except Exception as err:
            raise MarketDataException(f"Failed to get daily open close for {ticker} on {date}", err)
