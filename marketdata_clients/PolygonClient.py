from datetime import datetime, timedelta
from decimal import Decimal
import polygon
import logging
import asyncio
from marketdata_clients.BaseMarketDataClient import BaseMarketDataClient

logger = logging.getLogger(__name__)

POLYGON_CLIENT_NAME: str = "polygon"

class PolygonClient(BaseMarketDataClient):
    DEFAULT_THROTTLE_LIMIT = 12
    OPTION_THROTTLE_LIMIT = 0
    stocks_data = {}

    def __init__(self, json_content: dict, stage: str, throttle_limit=DEFAULT_THROTTLE_LIMIT):
        self.client_name = POLYGON_CLIENT_NAME
        self._load_key_secret(json_content, stage)
        self.THROTTLE_LIMIT = throttle_limit
        self.client = polygon.StocksClient(self._my_key)
        self.options_client = polygon.OptionsClient(self._my_key)
        logger.debug("PolygonClient created")

    def get_previous_close(self, ticker):
        self._wait_for_no_throttle(self.DEFAULT_THROTTLE_LIMIT)
        response = self.client.get_previous_close(ticker)
        logger.debug(f"get_previous_close response: {response}")
        return Decimal(response['results'][0]['c'])

    def get_grouped_daily_bars(self, date=None):
        self._wait_for_no_throttle(self.DEFAULT_THROTTLE_LIMIT)
        if date is None:
            date = self.get_previous_market_open_day()
        response = self.client.get_grouped_daily_bars(date=date)
        logger.debug(f"get_grouped_daily_bars response: {response}")
        self._populate_daily_bars(response['results'])
        return self.stocks_data

    def get_snapshot(self, symbol):
        self._wait_for_no_throttle(self.DEFAULT_THROTTLE_LIMIT)
        response = self.client.get_snapshot(symbol)
        logger.debug(f"get_snapshot response: {response}")
        return response['results']

    def get_option_previous_close(self, ticker):
        self._wait_for_no_throttle(self.OPTION_THROTTLE_LIMIT)
        response = self.options_client.get_previous_close(ticker)
        logger.debug(f"get_option_previous_close response: {response}")
        return Decimal(response['results'][0]['c'])

    async def _async_get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self._wait_for_no_throttle(self.OPTION_THROTTLE_LIMIT)
        contracts = polygon.ReferenceClient(self._my_key).get_option_contracts(
            underlying_ticker=underlying_ticker,
            expiration_date_lte=expiration_date_lte,
            expiration_date_gte=expiration_date_gte,
            contract_type=contract_type,
            order=order,
            sort='strike_price',
            all_pages=True
        )
        logger.debug(f"_async_get_option_contracts response: {contracts}")
        return contracts

    def get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self._wait_for_no_throttle(self.OPTION_THROTTLE_LIMIT)
        return asyncio.run(self._async_get_option_contracts(underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order))

    def get_option_snapshot(self, underlying_symbol: str, option_symbol: str = None):
        self._wait_for_no_throttle(self.OPTION_THROTTLE_LIMIT)
        response = self.options_client.get_snapshot(
            underlying_symbol=underlying_symbol,
            option_symbol=option_symbol,
            all_pages=False,
            max_pages=None,
            merge_all_pages=True,
            verbose=False,
            raw_page_responses=False,
            raw_response=False,
        )
        logger.debug(f"get_option_snapshot response: {response}")
        return response['results']
        
    def _populate_daily_bars(self, grouped_daily_bars):
        for bar in grouped_daily_bars:
            ticker = bar['T']
            date = datetime.fromtimestamp(bar['t'] / 1000).date()
            daily_bar = {
                "date": date,
                "open": Decimal(bar['o']),
                "high": Decimal(bar['h']),
                "low": Decimal(bar['l']),
                "close": Decimal(bar['c']),
                "volume": Decimal(bar['v'])
            }
            if ticker not in self.stocks_data:
                self.stocks_data[ticker] = {}
            self.stocks_data[ticker] = daily_bar