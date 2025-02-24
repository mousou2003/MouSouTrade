import polygon
import time
import logging
import asyncio
from marketdata_clients.MarketDataClient import MarketDataException, MarketDataClient

logger = logging.getLogger(__name__)

class PolygonClient(MarketDataClient):
    CLIENT_NAME = "polygon"
    instance = None
    DEFAULT_THROTTLE_LIMIT = 12

    def __new__(cls, throttle_limit=DEFAULT_THROTTLE_LIMIT):
        if PolygonClient.instance is None:
            logger.debug("Creating PolygonClient Singleton")
            PolygonClient.instance = super(PolygonClient, cls).__new__(cls)
            try:
                PolygonClient.instance.THROTTLE_LIMIT = throttle_limit
                PolygonClient.instance.client = polygon.StocksClient(PolygonClient.instance._my_key)
                PolygonClient.instance.options_client = polygon.OptionsClient(PolygonClient.instance._my_key)
                logger.debug("PolygonClient Singleton created")
            except Exception as e:
                logger.error(f"Failed to create PolygonClient: {e}")
                raise
        return PolygonClient.instance

    def get_previous_close(self, ticker):
        self._wait_for_no_throttle()
        return self._exponential_backoff(self.client.get_previous_close, ticker)

    def get_grouped_daily_bars(self, date):
        self._wait_for_no_throttle()
        return self._exponential_backoff(self.client.get_grouped_daily_bars, date=date)

    def get_snapshot(self, symbol):
        self._wait_for_no_throttle()
        return self._exponential_backoff(self.client.get_snapshot, symbol)

    def get_option_previous_close(self, ticker):
        self._wait_for_no_throttle()
        return self._exponential_backoff(self.options_client.get_previous_close, ticker)

    def get_grouped_option_daily_bars(self, date):
        self._wait_for_no_throttle()
        return self._exponential_backoff(self.options_client.get_grouped_daily_bars, date=date)

    async def async_get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self._wait_for_no_throttle()
        try:
            contracts = polygon.ReferenceClient(self._my_key).get_option_contracts(
                underlying_ticker=underlying_ticker,
                expiration_date_lte=expiration_date_lte,
                expiration_date_gte=expiration_date_gte,
                contract_type=contract_type,
                order=order,
                sort='strike_price',
                all_pages=True
            )
            if len(contracts) == 0:
                logger.warning(f"No option contracts found for {underlying_ticker}")
                return []
            return contracts
        except KeyError as err:
            logger.warning(f"No option contracts found for {underlying_ticker}: {err}")
            return []
        except Exception as err:
            raise MarketDataException(f"Failed to asynchronously get option contracts for {underlying_ticker}", err)

    def get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self._wait_for_no_throttle()
        return asyncio.run(self.async_get_option_contracts(underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order))

    def get_option_snapshot(self, symbol, option_symbol=None):
        self._wait_for_no_throttle()
        return self._exponential_backoff(
            self.options_client.get_snapshot,
            underlying_symbol=symbol,
            option_symbol=option_symbol
        )