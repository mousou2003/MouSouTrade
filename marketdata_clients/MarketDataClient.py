import logging
import json
import time
import datetime
from decimal import Decimal
from abc import ABC, abstractmethod
from marketdata_clients.PolygonClient import PolygonClient

logger = logging.getLogger(__name__)

class IMarketDataClient(ABC):
    @abstractmethod
    def get_previous_close(self, ticker):
        pass

    @abstractmethod
    def get_snapshot(self, symbol):
        pass

    @abstractmethod
    def get_grouped_daily_bars(self, date):
        pass

    @abstractmethod
    def get_option_previous_close(self, ticker):
        pass

    @abstractmethod
    def get_option_snapshot(self, symbol, option_symbol=None):
        pass

    @abstractmethod
    def get_grouped_option_daily_bars(self, date):
        pass

    @abstractmethod
    def get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        pass

    @abstractmethod
    def get_previous_market_open_day(self, date=None):
        pass

class MarketDataClient(IMarketDataClient):
    client_name = None
    client = None

    def __new__(cls, client_name):
        logger.debug("create MarketDataClient")
        instance = super(MarketDataClient, cls).__new__(cls)
        instance.client_name = client_name
        instance._load_key_secret(jsonfile="./config/SecurityKeys.json", stage="Sandbox")
        if client_name == PolygonClient.CLIENT_NAME:
            instance.client = PolygonClient(instance._my_key, instance._my_secret)
        return instance

    def get_previous_close(self, ticker):
        return self._exponential_backoff(self.client.get_previous_close, ticker)

    def get_grouped_daily_bars(self, date):
        return self._exponential_backoff(self.client.get_grouped_daily_bars, date=date)
    
    def get_snapshot(self, symbol):
        return self._exponential_backoff(self.client.get_snapshot, symbol)

    def get_option_previous_close(self, ticker):
        return self._exponential_backoff(self.client.get_option_previous_close, ticker)

    def get_grouped_option_daily_bars(self, date):
        return self._exponential_backoff(self.client.get_grouped_option_daily_bars, date=date)

    def get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        return self._exponential_backoff(
            self.client.get_option_contracts,
            underlying_ticker=underlying_ticker,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
            contract_type=contract_type,
            order=order
        )

    def get_option_snapshot(self, symbol, option_symbol=None):
        return self._exponential_backoff(
            self.client.get_snapshot,
            underlying_symbol=symbol,
            option_symbol=option_symbol
        )

    def get_previous_market_open_day(self, date=None):
        date = date if date else datetime.datetime.now().date()
        while True:
            date -= datetime.timedelta(days=1)
            if date.weekday() < 5:  # Monday to Friday are considered market open days
                return date

    def _load_key_secret(self, jsonfile, stage):
        with open(jsonfile) as file:
            clients = json.load(file)
            logger.debug("loaded json")
            self._my_key = clients["Clients"][self.client_name][stage]["Key"]
            self._my_secret = clients["Clients"][self.client_name][stage]["Secret"]

    def _wait_for_no_throttle(self):
        time.sleep(self.THROTTLE_LIMIT)

    def _exponential_backoff(self, func, *args, retries=3, **kwargs):
        for attempt in range(retries):
            try:
                return func(*args, **kwargs)
            except Exception as err:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise err

    def _populate_daily_bars(self, grouped_daily_bars):
        for bar in grouped_daily_bars:
            ticker = bar['T']
            date = datetime.datetime.fromtimestamp(bar['t'] / 1000).date()
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

class MarketDataException(Exception):
    def __init__(self, message, inner_exception=None):
        super().__init__(message)
        self.inner_exception = inner_exception

class MarketDataStrikeNotFoundException(MarketDataException):
    def __init__(self, message, inner_exception=None):
        super().__init__(message, inner_exception)
        self.inner_exception = inner_exception

class MarketDataStorageFailedException(MarketDataException):
    def __init__(self, message, inner_exception=None):
        super().__init__(message, inner_exception)
        self.inner_exception = inner_exception