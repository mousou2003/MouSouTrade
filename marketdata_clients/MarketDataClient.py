import logging
import json
logger = logging.getLogger(__name__)

class MarketDataClient(object):
    
    instance = None
    client_name = None

    def __new__(cls):
        if MarketDataClient.instance == None :
            logger.debug("Creating MarketDataClient Singleton")
            MarketDataClient.instance = super(MarketDataClient, cls).__new__(cls)
            logger.debug("MarketDataClient Singleton created")
        return MarketDataClient.instance
    
    def __init__(self, client_name) -> None:
        logger.info("Init MarketDataClient")

    def __del__(self):
        MarketDataClient.release()

    def release():
        logger.debug("release MarketDataClient")
        MarketDataClient.instance = None

    def get_daily_open_close(self, ticker, date):
        pass

    def get_option_previous_close(self, ticker):
        pass

    def get_grouped_stock_daily_bars(self,date):
        pass

    def get_grouped_option_daily_bars(self, date):
        pass

    async def async_get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte,  contract_type, order):
        pass

    def get_option_contracts(self,underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        pass

    def convert_option_symbol_formats(self, ticker):
        pass

    def load_key_secret(jsonfile, stage, client_name):
        MarketDataClient.client_name = client_name
        with open(jsonfile) as file:
            clients = json.load(file)
            logger.info("loaded json")        
            MarketDataClient._my_key= clients["Clients"][MarketDataClient.client_name][stage]["Key"]
            MarketDataClient._my_secret = clients["Clients"][MarketDataClient.client_name][stage]["Secret"]

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
