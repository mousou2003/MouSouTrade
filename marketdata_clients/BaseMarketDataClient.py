import logging
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal

from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class IMarketDataClient(ABC):

    @abstractmethod
    def get_previous_close(self, ticker):
        raise NotImplementedError

    @abstractmethod
    def get_snapshot(self, symbol):
        raise NotImplementedError

    @abstractmethod
    def get_grouped_daily_bars(self, date):
        raise NotImplementedError

    @abstractmethod
    def get_option_previous_close(self, ticker):
        raise NotImplementedError

    @abstractmethod
    def get_option_snapshot(self, underlying_ticker, option_symbol=None):
        raise NotImplementedError

    @abstractmethod
    def get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        raise NotImplementedError

    @abstractmethod
    def get_previous_market_open_day(self, date=None):
        raise NotImplementedError

class BaseMarketDataClient(IMarketDataClient, ABC):
    client_name: str = None
    _my_key: str = None
    _my_secret: str = None
    
    def get_previous_market_open_day(self, date=None):
        date = date if date else datetime.now().date()
        days_checked = 0
        while days_checked < 7:
            date -= timedelta(days=1)
            days_checked += 1
            if date.weekday() < 5:  # Monday to Friday are considered market open days
                return date
        raise IndexError("Failed to find a previous market open day within the last 7 days")
    
    def _load_key_secret(self, json_content, stage):
        clients = json_content
        logger.debug("load secrets")
        self._my_key = clients["Clients"][self.client_name][stage]["Key"]
        self._my_secret = clients["Clients"][self.client_name][stage]["Secret"]

    def _wait_for_no_throttle(self, wait_time=0):
        time.sleep(wait_time)

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